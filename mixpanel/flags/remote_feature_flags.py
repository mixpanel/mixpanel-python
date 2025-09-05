import httpx
import logging
import json
import urllib.parse
import asyncio
from datetime import datetime 
from typing import Dict, Any, Callable
from asgiref.sync import sync_to_async

from .types import RemoteFlagsConfig, SelectedVariant, RemoteFlagsResponse
from concurrent.futures import ThreadPoolExecutor
from .utils import REQUEST_HEADERS, EXPOSURE_EVENT, prepare_common_query_params

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)

class RemoteFeatureFlagsProvider:
    FLAGS_URL_PATH = "/flags"

    def __init__(self, token: str, config: RemoteFlagsConfig, version: str, tracker: Callable) -> None:
        self._token: str = token
        self._config: RemoteFlagsConfig = config
        self._version: str = version
        self._tracker: Callable = tracker
        self._executor: ThreadPoolExecutor = config.custom_executor or ThreadPoolExecutor(max_workers=5)

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.request_timeout_in_seconds),
        }

        self._async_client: httpx.AsyncClient = httpx.AsyncClient(**httpx_client_parameters)
        self._sync_client: httpx.Client = httpx.Client(**httpx_client_parameters)
        self._request_params_base = prepare_common_query_params(self._token, version)

    async def aget_variant_value(self, flag_key: str, fallback_value: Any, context: Dict[str, Any]) -> Any:
        variant = await self.aget_variant(flag_key, SelectedVariant(variant_value=fallback_value), context)
        return variant.variant_value

    async def aget_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any]) -> SelectedVariant:
        try:
            params = self._prepare_query_params(flag_key, context)
            start_time = datetime.now()
            response = await self._async_client.get(self.FLAGS_URL_PATH, params=params)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)
            selected_variant, is_fallback = self._handle_response(flag_key, fallback_value, response)

            if not is_fallback and (distinct_id := context.get("distinct_id")):
                properties = self._build_tracking_properties(flag_key, selected_variant, start_time, end_time)
                asyncio.create_task(
                    sync_to_async(self._tracker, executor=self._executor, thread_sensitive=False)(distinct_id, EXPOSURE_EVENT, properties))

            return selected_variant
        except Exception:
            logging.exception(f"Failed to get remote variant for flag '{flag_key}'")
            return fallback_value

    async def ais_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        variant_value = await self.aget_variant_value(flag_key, False, context)
        return bool(variant_value)

    def get_variant_value(self, flag_key: str, fallback_value: Any, context: Dict[str, Any]) -> Any:
        variant = self.get_variant(flag_key, SelectedVariant(variant_value=fallback_value), context)
        return variant.variant_value

    def get_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any]) -> SelectedVariant:
        try:
            params = self._prepare_query_params(flag_key, context)
            start_time = datetime.now()
            response = self._sync_client.get(self.FLAGS_URL_PATH, params=params)
            end_time = datetime.now()
            self._instrument_call(start_time, end_time)
            selected_variant, is_fallback = self._handle_response(flag_key, fallback_value, response)

            if not is_fallback and (distinct_id := context.get("distinct_id")):
                properties = self._build_tracking_properties(flag_key, selected_variant, start_time, end_time)
                self._executor.submit(self._tracker, distinct_id, EXPOSURE_EVENT, properties)

            return selected_variant
        except Exception:
            logging.exception(f"Failed to get remote variant for flag '{flag_key}'")
            return fallback_value

    def is_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        variant_value = self.get_variant_value(flag_key, False, context)
        return bool(variant_value)

    def _prepare_query_params(self, flag_key: str, context: Dict[str, Any]) -> Dict[str, str]:
        params = self._request_params_base.copy()
        context_json = json.dumps(context).encode('utf-8')
        url_encoded_context = urllib.parse.quote(context_json)
        params.update({
            'flag_key': flag_key,
            'context': url_encoded_context
        })
        return params

    def _instrument_call(self, start_time: datetime, end_time: datetime) -> None:
        request_duration = end_time - start_time
        formatted_start_time = start_time.isoformat()
        formatted_end_time = end_time.isoformat()
        logging.info(f"Request started at '{formatted_start_time}', completed at '{formatted_end_time}', duration: '{request_duration.total_seconds():.3f}s'")

    def _build_tracking_properties(self, flag_key: str, variant: SelectedVariant, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        request_duration = end_time - start_time
        formatted_start_time = start_time.isoformat()
        formatted_end_time = end_time.isoformat()

        return {
            'Experiment name': flag_key,
            'Variant name': variant.variant_key,
            '$experiment_type': 'feature_flag',
            "Flag evaluation mode": "remote",
            "Variant fetch start time": formatted_start_time,
            "Variant fetch complete time": formatted_end_time,
            "Variant fetch latency (ms)": request_duration.total_seconds() * 1000,
        }

    def _handle_response(self, flag_key: str, fallback_value: SelectedVariant, response: httpx.Response) -> tuple[SelectedVariant, bool]:
        response.raise_for_status()

        flags_response = RemoteFlagsResponse.model_validate(response.json())

        if flag_key in flags_response.flags:
            return flags_response.flags[flag_key], False
        else:
            logging.warning(f"Flag '{flag_key}' not found in remote response. Returning fallback, '{fallback_value}'")
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
