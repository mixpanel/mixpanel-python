from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from datetime import datetime
from typing import Any, Callable

import httpx
from asgiref.sync import sync_to_async

from .types import RemoteFlagsConfig, RemoteFlagsResponse, SelectedVariant
from .utils import (
    EXPOSURE_EVENT,
    REQUEST_HEADERS,
    generate_traceparent,
    prepare_common_query_params,
)

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

    async def aget_all_variants(
        self, context: dict[str, Any]
    ) -> dict[str, SelectedVariant] | None:
        """Asynchronously get all feature flag variants for the current user context from remote server.

        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :return: A dictionary mapping flag keys to their selected variants, or None if the call fails
        """
        flags: dict[str, SelectedVariant] | None = None
        try:
            params = self._prepare_query_params(context)
            start_time = datetime.now()  # noqa: DTZ005
            headers = {"traceparent": generate_traceparent()}
            response = await self._async_client.get(
                self.FLAGS_URL_PATH, params=params, headers=headers
            )
            end_time = datetime.now()  # noqa: DTZ005
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
        except Exception:
            logger.exception("Failed to get remote variants")

        return flags

    async def aget_variant_value(
        self, flag_key: str, fallback_value: Any, context: dict[str, Any]
    ) -> Any:
        """Get the selected variant value of a feature flag variant for the current user context from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param Any fallback_value: The default value to return if the flag is not found or evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant = await self.aget_variant(
            flag_key, SelectedVariant(variant_value=fallback_value), context
        )
        return variant.variant_value

    async def aget_variant(
        self,
        flag_key: str,
        fallback_value: SelectedVariant,
        context: dict[str, Any],
        reportExposure: bool = True,  # noqa: N803 - matches public API convention
    ) -> SelectedVariant:
        """Asynchronously get the selected variant of a feature flag variant for the current user context from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param SelectedVariant fallback_value: The default variant to return if evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :param bool reportExposure: Whether to report an exposure event if a variant is successfully retrieved
        """
        try:
            params = self._prepare_query_params(context, flag_key)
            start_time = datetime.now()  # noqa: DTZ005
            headers = {"traceparent": generate_traceparent()}
            response = await self._async_client.get(
                self.FLAGS_URL_PATH, params=params, headers=headers
            )
            end_time = datetime.now()  # noqa: DTZ005
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
            selected_variant, is_fallback = self._lookup_flag_in_response(
                flag_key, flags, fallback_value
            )

            if (
                not is_fallback
                and reportExposure
                and (distinct_id := context.get("distinct_id"))
            ):
                properties = self._build_tracking_properties(
                    flag_key, selected_variant, start_time, end_time
                )
                asyncio.create_task(  # noqa: RUF006 - intentional fire-and-forget for exposure tracking
                    sync_to_async(self._tracker, thread_sensitive=False)(
                        distinct_id, EXPOSURE_EVENT, properties
                    )
                )
        except Exception:
            logger.exception("Failed to get remote variant for flag '%s'", flag_key)
            return fallback_value
        else:
            return selected_variant

    async def ais_enabled(self, flag_key: str, context: dict[str, Any]) -> bool:
        """Asynchronously check if a feature flag is enabled for the given context.

        :param str flag_key: The key of the feature flag to check
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant_value = await self.aget_variant_value(flag_key, False, context)
        return variant_value is True

    async def atrack_exposure_event(
        self, flag_key: str, variant: SelectedVariant, context: dict[str, Any]
    ):
        """Manually track a feature flagging exposure event asynchronously to Mixpanel.

        This is intended to provide flexibility for when individual exposure events are reported when using `get_all_variants` for the user at once with exposure event reporting.

        :param str flag_key: The key of the feature flag
        :param SelectedVariant variant: The selected variant for the feature flag
        :param Dict[str, Any] context: The user context used to evaluate the feature flag
        """
        if distinct_id := context.get("distinct_id"):
            properties = self._build_tracking_properties(flag_key, variant)

            await sync_to_async(self._tracker, thread_sensitive=False)(
                distinct_id, EXPOSURE_EVENT, properties
            )
        else:
            logger.error(
                "Cannot track exposure event without a distinct_id in the context"
            )

    def get_all_variants(
        self, context: dict[str, Any]
    ) -> dict[str, SelectedVariant] | None:
        """Synchronously get all feature flag variants for the current user context from remote server.

        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :return: A dictionary mapping flag keys to their selected variants, or None if the call fails
        """
        flags: dict[str, SelectedVariant] | None = None
        try:
            params = self._prepare_query_params(context)
            start_time = datetime.now()  # noqa: DTZ005
            headers = {"traceparent": generate_traceparent()}
            response = self._sync_client.get(
                self.FLAGS_URL_PATH, params=params, headers=headers
            )
            end_time = datetime.now()  # noqa: DTZ005
            self._instrument_call(start_time, end_time)
            flags = self._handle_response(response)
        except Exception:
            logger.exception("Failed to get remote variants")

        return flags

    def get_variant_value(
        self, flag_key: str, fallback_value: Any, context: dict[str, Any]
    ) -> Any:
        """Synchronously get the value of a feature flag variant from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param Any fallback_value: The default value to return if the flag is not found or evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant = self.get_variant(
            flag_key, SelectedVariant(variant_value=fallback_value), context
        )
        return variant.variant_value

    def get_variant(
        self,
        flag_key: str,
        fallback_value: SelectedVariant,
        context: dict[str, Any],
        reportExposure: bool = True,  # noqa: N803 - matches public API convention
    ) -> SelectedVariant:
        """Synchronously get the selected variant for a feature flag from remote server.

        :param str flag_key: The key of the feature flag to evaluate
        :param SelectedVariant fallback_value: The default variant to return if evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        :param bool reportExposure: Whether to report an exposure event if a variant is successfully retrieved
        """
        try:
            params = self._prepare_query_params(context, flag_key)
            start_time = datetime.now()  # noqa: DTZ005
            headers = {"traceparent": generate_traceparent()}
            response = self._sync_client.get(
                self.FLAGS_URL_PATH, params=params, headers=headers
            )
            end_time = datetime.now()  # noqa: DTZ005
            self._instrument_call(start_time, end_time)

            flags = self._handle_response(response)
            selected_variant, is_fallback = self._lookup_flag_in_response(
                flag_key, flags, fallback_value
            )

            if (
                not is_fallback
                and reportExposure
                and (distinct_id := context.get("distinct_id"))
            ):
                properties = self._build_tracking_properties(
                    flag_key, selected_variant, start_time, end_time
                )
                self._tracker(distinct_id, EXPOSURE_EVENT, properties)

        except Exception:
            logger.exception("Failed to get remote variant for flag '%s'", flag_key)
            return fallback_value
        else:
            return selected_variant

    def is_enabled(self, flag_key: str, context: dict[str, Any]) -> bool:
        """Synchronously check if a feature flag is enabled for the given context.

        :param str flag_key: The key of the feature flag to check
        :param Dict[str, Any] context: Context dictionary containing user attributes and rollout context
        """
        variant_value = self.get_variant_value(flag_key, False, context)
        return variant_value is True

    def track_exposure_event(
        self, flag_key: str, variant: SelectedVariant, context: dict[str, Any]
    ):
        """Manually track a feature flagging exposure event synchronously to Mixpanel.

        This is intended to provide flexibility for when individual exposure events are reported when using `get_all_variants` for the user at once with exposure event reporting.

        :param str flag_key: The key of the feature flag
        :param SelectedVariant variant: The selected variant for the feature flag
        :param Dict[str, Any] context: The user context used to evaluate the feature flag
        """
        if distinct_id := context.get("distinct_id"):
            properties = self._build_tracking_properties(flag_key, variant)
            self._tracker(distinct_id, EXPOSURE_EVENT, properties)
        else:
            logger.error(
                "Cannot track exposure event without a distinct_id in the context"
            )

    def _prepare_query_params(
        self, context: dict[str, Any], flag_key: str | None = None
    ) -> dict[str, str]:
        params = self._request_params_base.copy()
        context_json = json.dumps(context).encode("utf-8")
        url_encoded_context = urllib.parse.quote(context_json)
        params["context"] = url_encoded_context
        if flag_key is not None:
            params["flag_key"] = flag_key
        return params

    def _instrument_call(self, start_time: datetime, end_time: datetime) -> None:
        request_duration = end_time - start_time
        logger.debug(
            "Request started at '%s', completed at '%s', duration: '%.3fs'",
            start_time.isoformat(),
            end_time.isoformat(),
            request_duration.total_seconds(),
        )

    def _build_tracking_properties(
        self,
        flag_key: str,
        variant: SelectedVariant,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        tracking_properties: dict[str, Any] = {
            "Experiment name": flag_key,
            "Variant name": variant.variant_key,
            "$experiment_type": "feature_flag",
            "Flag evaluation mode": "remote",
        }

        if start_time is not None and end_time is not None:
            request_duration = end_time - start_time
            formatted_start_time = start_time.isoformat()
            formatted_end_time = end_time.isoformat()

            tracking_properties.update(
                {
                    "Variant fetch start time": formatted_start_time,
                    "Variant fetch complete time": formatted_end_time,
                    "Variant fetch latency (ms)": request_duration.total_seconds()
                    * 1000,
                }
            )

        return tracking_properties

    def _handle_response(self, response: httpx.Response) -> dict[str, SelectedVariant]:
        response.raise_for_status()
        flags_response = RemoteFlagsResponse.model_validate(response.json())
        return flags_response.flags

    def _lookup_flag_in_response(
        self,
        flag_key: str,
        flags: dict[str, SelectedVariant],
        fallback_value: SelectedVariant,
    ) -> tuple[SelectedVariant, bool]:
        if flag_key in flags:
            return flags[flag_key], False
        logger.debug(
            "Flag '%s' not found in remote response. Returning fallback, '%s'",
            flag_key,
            fallback_value,
        )
        return fallback_value, True

    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        self._sync_client.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        await self._async_client.aclose()
