import httpx
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from .types import ExperimentationFlag, ExperimentationFlags, SelectedVariant, LocalFlagsConfig, Rollout
from .utils import REQUEST_HEADERS, normalized_hash, track_exposure_event

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)

class LocalFeatureFlagsProvider:
    FLAGS_DEFINITIONS_URL_PATH = "/flags/definitions"

    def __init__(self, token: str, config: LocalFlagsConfig, tracker: Callable) -> None:
        self._token: str = token
        self._config: LocalFlagsConfig = config
        self._tracker: Callable = tracker

        self._flag_definitions: Dict[str, ExperimentationFlag] = dict()

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.requestTimeoutInSeconds),
        }

        self.async_client: httpx.AsyncClient = httpx.AsyncClient(**httpx_client_parameters)

    async def start_polling_for_definitions(self):
        self._polling_task = asyncio.create_task(self._poll_for_definitions())

    async def _poll_for_definitions(self):
        await self._fetch_flag_definitions()

        if self._config.enablePolling:
            logging.info(f"Initialized async polling for flag definition updates every {self._config.pollingIntervalInSeconds} seconds")
            while True:
                await asyncio.sleep(self._config.pollingIntervalInSeconds)
                await self._fetch_flag_definitions()

    def are_flags_ready(self) -> bool:
        """
        Check if flag definitions have been loaded and are ready for use.
        :return: True if flag definitions are populated, False otherwise.
        """
        return bool(self._flag_definitions)

    def get_variant_value(self, flag_key: str, fallback_value: str, context: Dict[str, str]) -> str:
        variant = self.get_variant(flag_key, SelectedVariant(variant_key=fallback_value, variant_value=fallback_value), context)
        return variant.variant_value

    def is_enabled(self, flag_key: str, context: Dict[str, str]) -> bool:
        variant = self.get_variant_value(flag_key, False, context)
        return bool(variant)

    def get_variant(self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, str]) -> SelectedVariant:
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

    def _get_variant_override_for_test_user(self, flag_definition: ExperimentationFlag, context: Dict[str, str]) -> Optional[SelectedVariant]:
        """"""
        if not flag_definition.ruleset.test or not flag_definition.ruleset.test.users:
            return None

        if not (distinct_id := context.get("distinct_id")):
            return None

        if not (variant_key := flag_definition.ruleset.test.users.get(distinct_id)):
            return None

        for variant in flag_definition.ruleset.variants:
            if variant_key.casefold() == variant.key.casefold():
                return SelectedVariant(variant_key=variant.key, variant_value=variant.value)

        return None 

    def _get_assigned_variant(self, flag_definition: ExperimentationFlag, context_value: Any, flagName: str, rollout: Rollout) -> SelectedVariant:
        if rollout.variant_override:
            variant = rollout.variant_override
            return SelectedVariant(variant_key=variant.key, variant_value=variant.value)

        variants = flag_definition.ruleset.variants
        hash_input = str(context_value) + flagName

        variant_hash = normalized_hash(hash_input, "variant")

        selected = None
        last = None
        cumulative = 0.0
        for variant in variants:
            last = variant
            cumulative += variant.split
            if variant_hash < cumulative:
                selected = variant
                break

        chosen_variant = selected if selected else last

        return SelectedVariant(variant_key=chosen_variant.key, variant_value=chosen_variant.value)

    def _get_assigned_rollout(self, flag_definition: ExperimentationFlag, context_value: Any, context: Dict[str, str]) -> Optional[Rollout]:
        hash_input = str(context_value) + flag_definition.key

        rollout_hash = normalized_hash(hash_input, "rollout")

        for rollout in flag_definition.ruleset.rollout:
            if rollout_hash < rollout.rollout_percentage and self._is_runtime_evaluation_satisfied(rollout, context):
                return rollout

        return None

    def _is_runtime_evaluation_satisfied(self, rollout: Rollout, context: Dict[str, str]) -> bool:
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

    async def _fetch_flag_definitions(self) -> None:
        try:
            start_time = datetime.now()
            response = await self.async_client.get(self.FLAGS_DEFINITIONS_URL_PATH)
            end_time = datetime.now()
            request_duration: timedelta = end_time - start_time
            logging.info(f"Request started at {start_time.isoformat()}, completed at {end_time.isoformat()}, duration: {request_duration.total_seconds():.3f}s")

            response.raise_for_status()

            flags = {}
            try:
                json_data = response.json()
                experimentation_flags = ExperimentationFlags.model_validate(json_data)
                for flag in experimentation_flags.flags:
                    flags[flag.key] = flag
            except Exception as e:
                logger.error("Failed to parse flag definitions: {}".format(e))

            self._flag_definitions = flags
            logger.info("Successfully fetched {} flag definitions".format(len(self._flag_definitions)))
        except Exception as e:
            logger.error("Failed to fetch feature flag definitions: {}".format(e))

    def track_exposure(self, flag_key: str, variant: SelectedVariant, latencyInSeconds: float, context: Dict[str, str]):
        additional_properties = {
            "Flag evaluation mode": "remote",
            "Variant fetch latency (ms)": latencyInSeconds * 1000
        }

        if distinct_id := context.get("distinct_id"):
            track_exposure_event(
                distinct_id=distinct_id,
                flag_key=flag_key,
                variant=variant,
                additional_properties=additional_properties,
                tracker=self._tracker)
        else:
            logging.error("Cannot track exposure event without a distinct_id in the context")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Exiting the LocalFeatureFlagsProvider and cleaning up resources")
        if self._polling_task and not self._polling_task.done():
            await self._polling_task.cancel()

        await self.async_client.aclose()
