import httpx
import logging
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Any, Callable

from .types import RemoteFlagsConfig, SelectedVariant, RemoteFlagsResponse
from .utils import REQUEST_HEADERS, track_exposure_event, prepare_common_query_params
from .. import __version__

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)

class RemoteFeatureFlagsProvider:
    FLAGS_URL_PATH = "/flags"

    def __init__(self, token: str, config: RemoteFlagsConfig, tracker: Callable) -> None:
        self._config: RemoteFlagsConfig = config
        self._tracker: Callable = tracker

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.requestTimeoutInSeconds),
        }

        self.async_client: httpx.AsyncClient = httpx.AsyncClient(**httpx_client_parameters)
        self.sync_client: httpx.Client = httpx.Client(**httpx_client_parameters)

    async def aget_variant_value(self, flag_key: str, fallback_value: str, context: Dict[str, str]) -> SelectedVariant:
        variant = await self.aget_variant(flag_key, SelectedVariant(variant_key=fallback_value, variant_value=fallback_value), context)
        return variant.variant_value

    async def aget_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, str]) -> SelectedVariant:
        try:
            params = self._prepare_query_params(flag_key, context)
            start_time = datetime.now()
            response = await self.async_client.get(self.FLAGS_URL_PATH, params=params)
            end_time = datetime.now()
            return self._handle_response(context, flag_key, fallback_value, response, start_time, end_time)
        except Exception:
            logging.exception(f"Failed to get remote variant for flag {flag_key}")
            return fallback_value

    async def ais_enabled(self, flag_key: str, context: Dict[str, str]) -> bool:
        variant = await self.aget_variant_value(flag_key, "false", context)
        return bool(variant.variant_value)

    def get_variant_value(self, flag_key: str, fallback_value: Any, context: Dict[str, str]) -> SelectedVariant:
        variant = self.get_variant(flag_key, SelectedVariant(variant_key=fallback_value, variant_value=fallback_value), context)
        return variant.variant_value

    def get_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, str]) -> SelectedVariant:
        try:
            params = self._prepare_query_params(flag_key, context)
            start_time = datetime.now()
            response = self.sync_client.get(self.FLAGS_URL_PATH, params=params)
            end_time = datetime.now()
            return self._handle_response(context, flag_key, fallback_value, response, start_time, end_time)
        except Exception:
            logging.exception(f"Failed to get remote variant for flag {flag_key}")
            return fallback_value

    def is_enabled(self, flag_key: str, context: Dict[str, str]) -> bool:
        variant = self.get_variant_value(flag_key, "false", context)
        return bool(variant.variant_value)

    def _prepare_query_params(self, flag_key: str, context: Dict[str, str]) -> Dict[str, str]:
        params = prepare_common_query_params(self._token, __version__)
        context_json = json.dumps(context).encode('utf-8')
        url_encoded_context = urllib.parse.quote(context_json)
        params.update({
            'flag_key': flag_key,
            'context': url_encoded_context
        })
        return params

    def _handle_response(self, context: Dict[str, str], flag_key: str, fallback_value: SelectedVariant, response: httpx.Response, start_time: datetime, end_time: datetime) -> SelectedVariant:
        request_duration: timedelta = (end_time - start_time)
        formatted_start_time, formatted_end_time = start_time.isoformat(), end_time.isoformat()
        logging.info(f"Request started at {formatted_start_time}, completed at {formatted_end_time}, duration: {request_duration.total_seconds():.3f}s")

        response.raise_for_status()

        flags_response = RemoteFlagsResponse.model_validate(response.json())

        if flag_key in flags_response.flags:
            selected_variant = flags_response.flags[flag_key]

            additional_properties = {
                "Flag evaluation mode": "remote",
                "Variant fetch start time": formatted_start_time,
                "Variant fetch complete time": formatted_end_time,
                "Variant fetch latency (ms)": request_duration.total_seconds() * 1000,
            }

            if distinct_id := context.get("distinct_id"):
                track_exposure_event(
                    distinct_id=distinct_id,
                    flag_key=flag_key,
                    variant=selected_variant,
                    additional_properties=additional_properties,
                    tracker=self._tracker)

            return selected_variant
        else:
            logging.warning(f"Flag {flag_key} not found in remote response. Returning fallback, {fallback_value}")
            return fallback_value

    def __enter__(self):
        return self

    async def __aenter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        self.sync_client.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the RemoteFeatureFlagsProvider and cleaning up resources")
        await self.async_client.aclose()
