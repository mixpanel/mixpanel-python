import httpx
import logging
import json
import urllib.parse
import asyncio
from datetime import datetime
from typing import Dict, Any, Callable, Tuple, Optional
from asgiref.sync import sync_to_async

from .types import RemoteFlagsConfig, SelectedVariant, RemoteFlagsResponse
from .utils import REQUEST_HEADERS, EXPOSURE_EVENT, prepare_common_query_params, generate_traceparent 

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)


class RemoteFeatureFlagsProvider:
    FLAGS_URL_PATH = "/flags"

    def __init__(
        self, token: str, config: RemoteFlagsConfig, version: str, tracker: Callable
    ) -> None:
        self._token: str = token
        self._config: RemoteFlagsConfig = config
        self._version: str = version
        self._tracker: Callable = tracker

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.request_timeout_in_seconds),
        }

        self._async_client: httpx.AsyncClient = httpx.AsyncClient(
            **httpx_client_parameters
        )
        self._sync_client: httpx.Client = httpx.Client(**httpx_client_parameters)
        self._request_params_base = prepare_common_query_params(self._token, version)

    async def aget_all_variants(self, context: Dict[str, Any]) -> Optional[Dict[str, SelectedVariant]]:
        """
        Asynchronously gets all feature flag variants for the current user context from remote server.  
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :return: A dictionary mapping flag keys to their selected variants, or None if the call fails
        """
        flags: Optional[Dict[str, SelectedVariant]] = None
        try:
            params = self._prepare_query_params(context)
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = await self._async_client.get(self.FLAGS_URL_PATH, params=params, headers=headers)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
        except Exception:
            logger.exception(f"Failed to get remote variants")

        return flags

    async def aget_variant_value(
        self, flag_key: str, fallback_value: Any, context: Dict[str, Any]
    ) -> Any:
        """
        Gets the selected variant value of a feature flag variant for the current user context from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param Any fallback_value: The default value to return if the flag is not found or evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant = await self.aget_variant(
            flag_key, SelectedVariant(variant_value=fallback_value), context
        )
        return variant.variant_value

    async def aget_variant(
        self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any], reportExposure: bool = True
    ) -> SelectedVariant:
        """
        Asynchronously gets the selected variant  of a feature flag variant for the current user context from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param SelectedVariant fallback_value: The default variant to return if evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :param bool reportExposure: Whether to report an exposure event if a variant is successfully retrieved
        """
        try:
            params = self._prepare_query_params(context, flag_key)
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = await self._async_client.get(self.FLAGS_URL_PATH, params=params, headers=headers)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
            selected_variant, is_fallback = self._lookup_flag_in_response(flag_key, flags, fallback_value)

            if not is_fallback and reportExposure and (distinct_id := context.get("distinct_id")):
                properties = self._build_tracking_properties(
                    flag_key, selected_variant, start_time, end_time
                )
                asyncio.create_task(
                    sync_to_async(self._tracker, thread_sensitive=False)(
                        distinct_id, EXPOSURE_EVENT, properties
                    )
                )

            return selected_variant
        except Exception:
            logger.exception(f"Failed to get remote variant for flag '{flag_key}'")
            return fallback_value

    async def ais_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        """
        Asynchronously checks if a feature flag is enabled for the given context.

        :param str flag_key: The key of the feature flag to check
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant_value = await self.aget_variant_value(flag_key, False, context)
        return variant_value == True

    async def atrack_exposure_event(
        self,
        flag_key: str,
        variant: SelectedVariant,
        context: Dict[str, Any]):
        """
        Manually tracks a feature flagging exposure event asynchronously to Mixpanel.
        This is intended to provide flexibility for when individual exposure events are reported when using `get_all_variants` for the user at once with exposure event reporting

        :param str flag_key: The key of the feature flag
        :param SelectedVariant variant: The selected variant for the feature flag
        :param Dict[str, Any] context: The user context used to evaluate the feature flag
        """
        if (distinct_id := context.get("distinct_id")):
            properties = self._build_tracking_properties(flag_key, variant)

            await sync_to_async(self._tracker, thread_sensitive=False)(
                distinct_id, EXPOSURE_EVENT, properties
            )
        else:
            logger.error(
                "Cannot track exposure event without a distinct_id in the context"
            )


    def get_all_variants(self, context: Dict[str, Any]) -> Optional[Dict[str, SelectedVariant]]:
        """
        Synchronously gets all feature flag variants for the current user context from remote server.  
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :return: A dictionary mapping flag keys to their selected variants, or None if the call fails
        """
        flags: Optional[Dict[str, SelectedVariant]] = None
        try:
            params = self._prepare_query_params(context)
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = self._sync_client.get(self.FLAGS_URL_PATH, params=params, headers=headers)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
        except Exception:
            logger.exception(f"Failed to get remote variants")

        return flags

    def get_variant_value(
        self, flag_key: str, fallback_value: Any, context: Dict[str, Any]
    ) -> Any:
        """
        Synchronously gets the value of a feature flag variant from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param Any fallback_value: The default value to return if the flag is not found or evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant = self.get_variant(
            flag_key, SelectedVariant(variant_value=fallback_value), context
        )
        return variant.variant_value

    def get_variant(
        self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any], reportExposure: bool = True
    ) -> SelectedVariant:
        """
        Synchronously gets the selected variant for a feature flag from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param SelectedVariant fallback_value: The default variant to return if evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :param bool reportExposure: Whether to report an exposure event if a variant is successfully retrieved
        """
        try:
            params = self._prepare_query_params(context, flag_key)
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = self._sync_client.get(self.FLAGS_URL_PATH, params=params, headers=headers)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)

            flags = self._handle_response(response)
            selected_variant, is_fallback = self._lookup_flag_in_response(flag_key, flags, fallback_value)

            if not is_fallback and reportExposure and (distinct_id := context.get("distinct_id")):
                properties = self._build_tracking_properties(
                    flag_key, selected_variant, start_time, end_time
                )
                self._tracker(distinct_id, EXPOSURE_EVENT, properties)

            return selected_variant
        except Exception:
            logging.exception(f"Failed to get remote variant for flag '{flag_key}'")
            return fallback_value

    def is_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        """
        Synchronously checks if a feature flag is enabled for the given context.

        :param str flag_key: The key of the feature flag to check
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant_value = self.get_variant_value(flag_key, False, context)
        return variant_value == True

    def track_exposure_event(
        self,
        flag_key: str,
        variant: SelectedVariant,
        context: Dict[str, Any]):
        """
        Manually tracks a feature flagging exposure event synchronously to Mixpanel.
        This is intended to provide flexibility for when individual exposure events are reported when using `get_all_variants` for the user at once with exposure event reporting

        :param str flag_key: The key of the feature flag
        :param SelectedVariant variant: The selected variant for the feature flag
        :param Dict[str, Any] context: The user context used to evaluate the feature flag
        """
        if (distinct_id := context.get("distinct_id")):
            properties = self._build_tracking_properties(flag_key, variant)
            self._tracker(distinct_id, EXPOSURE_EVENT, properties)
        else:
            logging.error(
                "Cannot track exposure event without a distinct_id in the context"
            )

    def _prepare_query_params(
        self, context: Dict[str, Any], flag_key: Optional[str] = None
    ) -> Dict[str, str]:
        params = self._request_params_base.copy()
        context_json = json.dumps(context).encode("utf-8")
        url_encoded_context = urllib.parse.quote(context_json)
        params["context"] = url_encoded_context
        if flag_key is not None:
            params["flag_key"] = flag_key
        return params

    def _instrument_call(self, start_time: datetime, end_time: datetime) -> None:
        request_duration = end_time - start_time
        formatted_start_time = start_time.isoformat()
        formatted_end_time = end_time.isoformat()
        logging.debug(
            f"Request started at '{formatted_start_time}', completed at '{formatted_end_time}', duration: '{request_duration.total_seconds():.3f}s'"
        )

    def _build_tracking_properties(
        self,
        flag_key: str,
        variant: SelectedVariant,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        tracking_properties: Dict[str, Any] = {
            "Experiment name": flag_key,
            "Variant name": variant.variant_key,
            "$experiment_type": "feature_flag",
            "Flag evaluation mode": "remote",
        }

        if start_time is not None and end_time is not None:
            request_duration = end_time - start_time
            formatted_start_time = start_time.isoformat()
            formatted_end_time = end_time.isoformat()

            tracking_properties.update({
                "Variant fetch start time": formatted_start_time,
                "Variant fetch complete time": formatted_end_time,
                "Variant fetch latency (ms)": request_duration.total_seconds() * 1000,
            })

        return tracking_properties

    def _handle_response(self, response: httpx.Response) -> Dict[str, SelectedVariant]:
        response.raise_for_status()
        flags_response = RemoteFlagsResponse.model_validate(response.json())
        return flags_response.flags

    def _lookup_flag_in_response(self, flag_key: str, flags: Dict[str, SelectedVariant], fallback_value: SelectedVariant) -> Tuple[SelectedVariant, bool]:
        if flag_key in flags:
            return flags[flag_key], False
        else:
            logging.debug(
                f"Flag '{flag_key}' not found in remote response. Returning fallback, '{fallback_value}'"
            )
            return fallback_value, True


    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        self._sync_client.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        await self._async_client.aclose()
