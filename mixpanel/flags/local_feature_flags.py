import httpx
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
from .types import ExperimentationFlag, ExperimentationFlags, SelectedVariant, LocalFlagsConfig, Rollout
from .utils import REQUEST_HEADERS, normalized_hash, prepare_common_query_params, EXPOSURE_EVENT

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)

class LocalFeatureFlagsProvider:
    FLAGS_DEFINITIONS_URL_PATH = "/flags/definitions"

    def __init__(self, token: str, config: LocalFlagsConfig, version: str, tracker: Callable) -> None:
        self._token: str = token
        self._config: LocalFlagsConfig = config
        self._version = version
        self._tracker: Callable = tracker
        self._executor: ThreadPoolExecutor = config.custom_executor or ThreadPoolExecutor(max_workers=5)

        self._flag_definitions: Dict[str, ExperimentationFlag] = dict()

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.request_timeout_in_seconds),
        }

        self._request_params = prepare_common_query_params(self._token, self._version)

        self._async_client: httpx.AsyncClient = httpx.AsyncClient(**httpx_client_parameters)
        self._sync_client: httpx.Client = httpx.Client(**httpx_client_parameters)

        self._async_polling_task = None
        self._sync_polling_task = None

    def start_polling_for_definitions(self):
        self._fetch_flag_definitions()

        if self._config.enable_polling:
            if not self._sync_polling_task and not self._async_polling_task:
                self._sync_polling_task = self._executor.submit(self._start_continuous_polling)
            else:
                logging.error("A polling task is already running")

    async def astart_polling_for_definitions(self):
        await self._afetch_flag_definitions()

        if self._config.enable_polling:
            if not self._sync_polling_task and not self._async_polling_task:
                self._polling_task = asyncio.create_task(self._astart_continuous_polling())
            else:
                logging.error("A polling task is already running")

    async def _astart_continuous_polling(self):
        logging.info(f"Initialized async polling for flag definition updates every {self._config.polling_interval_in_seconds} seconds")
        while True:
            await asyncio.sleep(self._config.polling_interval_in_seconds)
            await self._afetch_flag_definitions()

    def _start_continuous_polling(self):
        logging.info(f"Initialized sync polling for flag definition updates every {self._config.polling_interval_in_seconds} seconds")
        while True:
            time.sleep(self._config.polling_interval_in_seconds)
            self._fetch_flag_definitions()

    def are_flags_ready(self) -> bool:
        """
        Check if flag definitions have been loaded and are ready for use.
        :return: True if flag definitions are populated, False otherwise.
        """
        return bool(self._flag_definitions)

    def get_variant_value(self, flag_key: str, fallback_value: Any, context: Dict[str, Any]) -> Any:
        variant = self.get_variant(flag_key, SelectedVariant(variant_key=fallback_value, variant_value=fallback_value), context)
        return variant.variant_value

    def is_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        variant = self.get_variant_value(flag_key, "false" , context)
        return bool(variant)

    def get_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any]) -> SelectedVariant:
        start_time = time.perf_counter()
        flag_definition = self._flag_definitions.get(flag_key)

        if not flag_definition:
            logger.warning(f"Cannot find flag definition for key: {flag_key}")
            return fallback_value

        if not(context_value := context.get(flag_definition.context)):
            logger.warning(f"The rollout context, {flag_definition.context} for flag, {flag_key} is not present in the supplied context dictionary")
            return fallback_value

        if test_user_variant := self._get_variant_override_for_test_user(flag_definition, context):
            return test_user_variant

        if rollout := self._get_assigned_rollout(flag_definition, context_value, context):
            variant = self._get_assigned_variant(flag_definition, context_value, flag_key, rollout)
            end_time = time.perf_counter()
            self.track_exposure(flag_key, variant, end_time - start_time, context)
            return variant

        logger.info(f"{flag_definition.context} context {context_value} not eligible for any rollout for flag: {flag_key}")
        return fallback_value

    def _get_variant_override_for_test_user(self, flag_definition: ExperimentationFlag, context: Dict[str, Any]) -> Optional[SelectedVariant]:
        """"""
        if not flag_definition.ruleset.test or not flag_definition.ruleset.test.users:
            return None

        if not (distinct_id := context.get("distinct_id")):
            return None

        if not (variant_key := flag_definition.ruleset.test.users.get(distinct_id)):
            return None

        return self._get_matching_variant(variant_key, flag_definition)

    def _get_assigned_variant(self, flag_definition: ExperimentationFlag, context_value: Any, flag_name: str, rollout: Rollout) -> SelectedVariant:
        if rollout.variant_override:
            if variant := self._get_matching_variant(rollout.variant_override.key, flag_definition):
                return variant

        variants = flag_definition.ruleset.variants

        hash_input = str(context_value) + flag_name

        variant_hash = normalized_hash(hash_input, "variant")

        selected = variants[0]
        cumulative = 0.0
        for variant in variants:
            selected = variant
            cumulative += variant.split
            if variant_hash < cumulative:
                break

        return SelectedVariant(variant_key=selected.key, variant_value=selected.value)

    def _get_assigned_rollout(self, flag_definition: ExperimentationFlag, context_value: Any, context: Dict[str, Any]) -> Optional[Rollout]:
        hash_input = str(context_value) + flag_definition.key

        rollout_hash = normalized_hash(hash_input, "rollout")

        for rollout in flag_definition.ruleset.rollout:
            if rollout_hash < rollout.rollout_percentage and self._is_runtime_evaluation_satisfied(rollout, context):
                return rollout

        return None

    def _is_runtime_evaluation_satisfied(self, rollout: Rollout, context: Dict[str, Any]) -> bool:
        if not rollout.runtime_evaluation_definition:
            return True

        if not (custom_properties := context.get("custom_properties")):
            return False

        if not isinstance(custom_properties, dict):
            return False

        for key, expected_value in rollout.runtime_evaluation_definition.items():
            if key not in custom_properties:
                return False

            actual_value = custom_properties[key]
            if actual_value.casefold() != expected_value.casefold():
                return False

        return True

    def _get_matching_variant(self, variant_key: str, flag: ExperimentationFlag) -> Optional[SelectedVariant]:
        for variant in flag.ruleset.variants:
            if variant_key.casefold() == variant.key.casefold():
                return SelectedVariant(variant_key=variant.key, variant_value=variant.value)
        return None

    async def _afetch_flag_definitions(self) -> None:
        try:
            start_time = datetime.now()
            response = await self._async_client.get(self.FLAGS_DEFINITIONS_URL_PATH, params=self._request_params)
            end_time = datetime.now()
            self._handle_response(response, start_time, end_time)
        except Exception as e:
            logger.error("Failed to fetch feature flag definitions: {}".format(e))

    def _fetch_flag_definitions(self) -> None:
        try:
            start_time = datetime.now()
            response = self._sync_client.get(self.FLAGS_DEFINITIONS_URL_PATH, params=self._request_params)
            end_time = datetime.now()
            self._handle_response(response, start_time, end_time)
        except Exception as e:
            logger.error("Failed to fetch feature flag definitions: {}".format(e))

    def _handle_response(self, response: httpx.Response, start_time: datetime, end_time: datetime) -> None:
        request_duration: timedelta = end_time - start_time
        logging.info(f"Request started at {start_time.isoformat()}, completed at {end_time.isoformat()}, duration: {request_duration.total_seconds():.3f}s")

        response.raise_for_status()

        flags = {}
        try:
            json_data = response.json()
            experimentation_flags = ExperimentationFlags.model_validate(json_data)
            for flag in experimentation_flags.flags:
                flag.ruleset.variants.sort(key=lambda variant: variant.key)
                flags[flag.key] = flag
        except Exception as e:
            logger.error("Failed to parse flag definitions: {}".format(e))

        self._flag_definitions = flags
        logger.info("Successfully fetched {} flag definitions".format(len(self._flag_definitions)))


    def track_exposure(self, flag_key: str, variant: SelectedVariant, latency_in_seconds: float, context: Dict[str, Any]):
        if distinct_id := context.get("distinct_id"):
            properties = {
                'Experiment name': flag_key,
                'Variant name': variant.variant_key,
                '$experiment_type': 'feature_flag',
                "Flag evaluation mode": "local",
                "Variant fetch latency (ms)": latency_in_seconds * 1000
            }
            self._executor.submit(self._tracker, distinct_id, EXPOSURE_EVENT, properties)
        else:
            logging.error("Cannot track exposure event without a distinct_id in the context")

    async def __aenter__(self):
        return self

    def __enter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the LocalFeatureFlagsProvider and cleaning up resources")
        if self._async_polling_task:
            result =  self._async_polling_task.cancel()
            logging.info(f"Polling task cancellation completed with result: {result}")

        await self._async_client.aclose()

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the LocalFeatureFlagsProvider and cleaning up resources")
        if self._sync_polling_task:
            result = self._sync_polling_task.cancel()
            logging.info(f"Polling task cancellation completed with result: {result}")

        self._sync_client.close()
        pass
