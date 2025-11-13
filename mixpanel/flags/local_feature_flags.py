import httpx
import logging
import asyncio
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional
from .types import (
    ExperimentationFlag,
    ExperimentationFlags,
    SelectedVariant,
    LocalFlagsConfig,
    Rollout,
)
from .utils import (
    REQUEST_HEADERS,
    normalized_hash,
    prepare_common_query_params,
    EXPOSURE_EVENT,
    generate_traceparent
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)


class LocalFeatureFlagsProvider:
    FLAGS_DEFINITIONS_URL_PATH = "/flags/definitions"

    def __init__(
        self, token: str, config: LocalFlagsConfig, version: str, tracker: Callable
    ) -> None:
        """
        Initializes the LocalFeatureFlagsProvider
        :param str token: your project's Mixpanel token
        :param LocalFlagsConfig config: configuration options for the local feature flags provider
        :param str version: the version of the Mixpanel library being used, just for tracking
        :param Callable tracker: A function used to track flags exposure events to mixpanel
        """
        self._token: str = token
        self._config: LocalFlagsConfig = config
        self._version = version
        self._tracker: Callable = tracker

        self._flag_definitions: Dict[str, ExperimentationFlag] = dict()
        self._are_flags_ready = False

        httpx_client_parameters = {
            "base_url": f"https://{config.api_host}",
            "headers": REQUEST_HEADERS,
            "auth": httpx.BasicAuth(token, ""),
            "timeout": httpx.Timeout(config.request_timeout_in_seconds),
        }

        self._request_params = prepare_common_query_params(self._token, self._version)

        self._async_client: httpx.AsyncClient = httpx.AsyncClient(
            **httpx_client_parameters
        )
        self._sync_client: httpx.Client = httpx.Client(**httpx_client_parameters)

        self._async_polling_task: Optional[asyncio.Task] = None
        self._sync_polling_task: Optional[threading.Thread] = None

        self._sync_stop_event = threading.Event()

    def start_polling_for_definitions(self):
        """
        Fetches flag definitions for the current project.
        If configured by the caller, starts a background thread to poll for updates at regular intervals, if one does not already exist.
        """
        self._fetch_flag_definitions()

        if self._config.enable_polling:
            if not self._sync_polling_task and not self._async_polling_task:
                self._sync_stop_event.clear()
                self._sync_polling_task = threading.Thread(
                    target=self._start_continuous_polling, daemon=True
                )
                self._sync_polling_task.start()
            else:
                logger.warning("A polling task is already running")

    def stop_polling_for_definitions(self):
        """
        If there exists a reference to a background thread polling for flag definition updates, signal it to stop and clear the reference.
        Once stopped, the polling thread cannot be restarted.
        """
        if self._sync_polling_task:
            self._sync_stop_event.set()
            self._sync_polling_task = None
        else:
            logger.info("There is no polling task to cancel.")

    async def astart_polling_for_definitions(self):
        """
        Fetches flag definitions for the current project.
        If configured by the caller, starts an async task on the event loop to poll for updates at regular intervals, if one does not already exist.
        """
        await self._afetch_flag_definitions()

        if self._config.enable_polling:
            if not self._sync_polling_task and not self._async_polling_task:
                self._async_polling_task = asyncio.create_task(
                    self._astart_continuous_polling()
                )
            else:
                logger.error("A polling task is already running")

    async def astop_polling_for_definitions(self):
        """
        If there exists an async task  to poll for flag definition updates, cancel the task and clear the reference to it.
        """
        if self._async_polling_task:
            self._async_polling_task.cancel()
            self._async_polling_task = None
        else:
            logger.info("There is no polling task to cancel.")

    async def _astart_continuous_polling(self):
        logger.info(
            f"Initialized async polling for flag definition updates every '{self._config.polling_interval_in_seconds}' seconds"
        )
        try:
            while True:
                await asyncio.sleep(self._config.polling_interval_in_seconds)
                await self._afetch_flag_definitions()
        except asyncio.CancelledError:
            logger.info("Async polling was cancelled")

    def _start_continuous_polling(self):
        logger.info(
            f"Initialized sync polling for flag definition updates every '{self._config.polling_interval_in_seconds}' seconds"
        )
        while not self._sync_stop_event.is_set():
            if self._sync_stop_event.wait(
                timeout=self._config.polling_interval_in_seconds
            ):
                break

            self._fetch_flag_definitions()

    def are_flags_ready(self) -> bool:
        """
        Check if the call to fetch flag definitions has been made successfully.
        """
        return self._are_flags_ready

    def get_all_variants(self, context: Dict[str, Any]) -> Dict[str, SelectedVariant]:
        """
        Gets the selected variant for all feature flags that the current user context is in the rollout for.
        Exposure events are not automatically tracked when this method is used.
        :param Dict[str, Any] context: The user context to evaluate against the feature flags
        """
        variants: Dict[str, SelectedVariant] = {}
        fallback = SelectedVariant(variant_key=None, variant_value=None)

        for flag_key in self._flag_definitions.keys():
            variant = self.get_variant(flag_key, fallback, context, report_exposure=False)
            if variant.variant_key is not None:
                variants[flag_key] = variant

        return variants

    def get_variant_value(
        self, flag_key: str, fallback_value: Any, context: Dict[str, Any]
    ) -> Any:
        """
        Get the value of a feature flag variant.

        :param str flag_key: The key of the feature flag to evaluate
        :param Any fallback_value: The default value to return if the flag is not found or evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user's distinct_id and any other attributes needed for rollout evaluation
        """
        variant = self.get_variant(
            flag_key, SelectedVariant(variant_value=fallback_value), context
        )
        return variant.variant_value

    def is_enabled(self, flag_key: str, context: Dict[str, Any]) -> bool:
        """
        Check if a feature flag is enabled for the given context.

        :param str flag_key: The key of the feature flag to check
        :param Dict[str, Any] context: Context dictionary containing user's distinct_id and any other attributes needed for rollout evaluation
        """
        variant_value = self.get_variant_value(flag_key, False, context)
        return variant_value == True

    def get_variant(
        self, flag_key: str, fallback_value: SelectedVariant, context: Dict[str, Any], report_exposure: bool = True
    ) -> SelectedVariant:
        """
        Gets the selected variant for a feature flag

        :param str flag_key: The key of the feature flag to evaluate
        :param SelectedVariant fallback_value: The default variant to return if evaluation fails
        :param Dict[str, Any] context: Context dictionary containing user's distinct_id and any other attributes needed for rollout evaluation
        :param bool report_exposure: Whether to track an exposure event for this flag evaluation. Defaults to True.
        """
        start_time = time.perf_counter()
        flag_definition = self._flag_definitions.get(flag_key)

        if not flag_definition:
            logger.warning(f"Cannot find flag definition for key: '{flag_key}'")
            return fallback_value

        if not (context_value := context.get(flag_definition.context)):
            logger.warning(
                f"The rollout context, '{flag_definition.context}' for flag, '{flag_key}' is not present in the supplied context dictionary"
            )
            return fallback_value

        selected_variant: Optional[SelectedVariant] = None

        if test_user_variant := self._get_variant_override_for_test_user(
            flag_definition, context
        ):
            selected_variant = test_user_variant
        elif rollout := self._get_assigned_rollout(flag_definition, context_value, context):
            selected_variant = self._get_assigned_variant(
                flag_definition, context_value, flag_key, rollout
            )

        if selected_variant is not None:
            if report_exposure:
                end_time = time.perf_counter()
                self._track_exposure(flag_key, selected_variant, context, end_time - start_time)
            return selected_variant

        logger.debug(
            f"{flag_definition.context} context {context_value} not eligible for any rollout for flag: {flag_key}"
        )
        return fallback_value

    def track_exposure_event(self, flag_key: str, variant: SelectedVariant, context: Dict[str, Any]):
        """
        Manually tracks a feature flagging exposure event to Mixpanel.
        This is intended to provide flexibility for when individual exposure events are reported when using `get_all_variants` for the user at once with exposure event reporting

        :param str flag_key: The key of the feature flag
        :param SelectedVariant variant: The selected variant for the feature flag
        :param Dict[str, Any] context: The user context used to evaluate the feature flag
        """
        self._track_exposure(flag_key, variant, context)

    def _get_variant_override_for_test_user(
        self, flag_definition: ExperimentationFlag, context: Dict[str, Any]
    ) -> Optional[SelectedVariant]:
        """"""
        if not flag_definition.ruleset.test or not flag_definition.ruleset.test.users:
            return None

        if not (distinct_id := context.get("distinct_id")):
            return None

        if not (variant_key := flag_definition.ruleset.test.users.get(distinct_id)):
            return None

        return self._get_matching_variant(variant_key, flag_definition)

    def _get_assigned_variant(
        self,
        flag_definition: ExperimentationFlag,
        context_value: Any,
        flag_name: str,
        rollout: Rollout,
    ) -> SelectedVariant:
        if rollout.variant_override:
            if variant := self._get_matching_variant(
                rollout.variant_override.key, flag_definition
            ):
                return variant

        stored_salt = flag_definition.hash_salt if flag_definition.hash_salt is not None else ""
        salt = flag_name + stored_salt + "variant"
        variant_hash = normalized_hash(str(context_value), salt)

        variants = [variant.model_copy(deep=True) for variant in flag_definition.ruleset.variants]
        if rollout.variant_splits:
            for variant in variants:
                if variant.key in rollout.variant_splits:
                    variant.split = rollout.variant_splits[variant.key]

        selected = variants[0]
        cumulative = 0.0
        for variant in variants:
            selected = variant
            cumulative += variant.split
            if variant_hash < cumulative:
                break

        return SelectedVariant(
            variant_key=selected.key,
            variant_value=selected.value,
            experiment_id=flag_definition.experiment_id,
            is_experiment_active=flag_definition.is_experiment_active)

    def _get_assigned_rollout(
        self,
        flag_definition: ExperimentationFlag,
        context_value: Any,
        context: Dict[str, Any],
    ) -> Optional[Rollout]:
        for index, rollout in enumerate(flag_definition.ruleset.rollout):
            salt = None
            if flag_definition.hash_salt is not None:
                salt = flag_definition.key + flag_definition.hash_salt + str(index)
            else:
                salt = flag_definition.key + "rollout"

            rollout_hash = normalized_hash(str(context_value), salt)

            if (rollout_hash < rollout.rollout_percentage
                and self._is_runtime_evaluation_satisfied(rollout, context)
            ):
                return rollout

        return None

    def _is_runtime_evaluation_satisfied(
        self, rollout: Rollout, context: Dict[str, Any]
    ) -> bool:
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

    def _get_matching_variant(
        self, variant_key: str, flag: ExperimentationFlag
    ) -> Optional[SelectedVariant]:
        for variant in flag.ruleset.variants:
            if variant_key.casefold() == variant.key.casefold():
                return SelectedVariant(
                    variant_key=variant.key,
                    variant_value=variant.value,
                    experiment_id=flag.experiment_id,
                    is_experiment_active=flag.is_experiment_active,
                    is_qa_tester=True,
                )
        return None

    async def _afetch_flag_definitions(self) -> None:
        try:
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = await self._async_client.get(
                self.FLAGS_DEFINITIONS_URL_PATH, params=self._request_params, headers=headers
            )
            end_time = datetime.now()
            self._handle_response(response, start_time, end_time)
        except Exception:
            logger.exception("Failed to fetch feature flag definitions")

    def _fetch_flag_definitions(self) -> None:
        try:
            start_time = datetime.now()
            headers = {"traceparent": generate_traceparent()}
            response = self._sync_client.get(
                self.FLAGS_DEFINITIONS_URL_PATH, params=self._request_params, headers=headers
            )
            end_time = datetime.now()
            self._handle_response(response, start_time, end_time)
        except Exception:
            logger.exception("Failed to fetch feature flag definitions")

    def _handle_response(
        self, response: httpx.Response, start_time: datetime, end_time: datetime
    ) -> None:
        request_duration: timedelta = end_time - start_time
        logger.debug(
            f"Request started at '{start_time.isoformat()}', completed at '{end_time.isoformat()}', duration: '{request_duration.total_seconds():.3f}s'"
        )

        response.raise_for_status()

        flags = {}
        try:
            json_data = response.json()
            experimentation_flags = ExperimentationFlags.model_validate(json_data)
            for flag in experimentation_flags.flags:
                flag.ruleset.variants.sort(key=lambda variant: variant.key)
                flags[flag.key] = flag
        except Exception:
            logger.exception("Failed to parse flag definitions")

        self._flag_definitions = flags
        self._are_flags_ready = True
        logger.debug(
            f"Successfully fetched {len(self._flag_definitions)} flag definitions"
        )

    def _track_exposure(
        self,
        flag_key: str,
        variant: SelectedVariant,
        context: Dict[str, Any],
        latency_in_seconds: Optional[float]=None,
    ):
        if distinct_id := context.get("distinct_id"):
            properties = {
                "Experiment name": flag_key,
                "Variant name": variant.variant_key,
                "$experiment_type": "feature_flag",
                "Flag evaluation mode": "local",
                "$experiment_id": variant.experiment_id,
                "$is_experiment_active": variant.is_experiment_active,
                "$is_qa_tester": variant.is_qa_tester,
            }

            if latency_in_seconds is not None:
                properties["Variant fetch latency (ms)"] = latency_in_seconds * 1000

            self._tracker(distinct_id, EXPOSURE_EVENT, properties)
        else:
            logger.error(
                "Cannot track exposure event without a distinct_id in the context"
            )

    async def __aenter__(self):
        return self

    def __enter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.info("Exiting the LocalFeatureFlagsProvider and cleaning up resources")
        await self.astop_polling_for_definitions()
        await self._async_client.aclose()

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.info("Exiting the LocalFeatureFlagsProvider and cleaning up resources")
        self.stop_polling_for_definitions()
        self._sync_client.close()
