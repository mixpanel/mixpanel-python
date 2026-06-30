from __future__ import annotations

import math
import typing
from typing import Union

from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata

from mixpanel import Mixpanel
from mixpanel.flags.types import (
    FallbackReason,
    LocalFlagsConfig,
    RemoteFlagsConfig,
    SelectedVariant,
)

if typing.TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from openfeature.evaluation_context import EvaluationContext

FlagValueType = Union[bool, str, int, float, list, dict, None]


class MixpanelProvider(AbstractProvider):
    """An OpenFeature provider backed by a Mixpanel feature flags provider."""

    def __init__(
        self,
        flags_provider: typing.Any,
        mixpanel_instance: Mixpanel | None = None,
    ) -> None:
        super().__init__()
        self._flags_provider = flags_provider
        self._mixpanel = mixpanel_instance

    @classmethod
    def from_local_config(
        cls, token: str, config: LocalFlagsConfig
    ) -> MixpanelProvider:
        """Create a MixpanelProvider backed by a local flags provider.

        :param str token: your project's Mixpanel token
        :param LocalFlagsConfig config: configuration for local feature flags
        """
        mp = Mixpanel(token, local_flags_config=config)
        local_flags = mp.local_flags
        local_flags.start_polling_for_definitions()
        return cls(local_flags, mixpanel_instance=mp)

    @classmethod
    def from_remote_config(
        cls, token: str, config: RemoteFlagsConfig
    ) -> MixpanelProvider:
        """Create a MixpanelProvider backed by a remote flags provider.

        :param str token: your project's Mixpanel token
        :param RemoteFlagsConfig config: configuration for remote feature flags
        """
        mp = Mixpanel(token, remote_flags_config=config)
        remote_flags = mp.remote_flags
        return cls(remote_flags, mixpanel_instance=mp)

    @property
    def mixpanel(self) -> Mixpanel | None:
        """The Mixpanel instance used by this provider, if created via a class method."""
        return self._mixpanel

    def get_metadata(self) -> Metadata:
        return Metadata(name="mixpanel-provider")

    def shutdown(self) -> None:
        self._flags_provider.shutdown()

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        return self._resolve(flag_key, default_value, bool, evaluation_context)

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[str]:
        return self._resolve(flag_key, default_value, str, evaluation_context)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[int]:
        return self._resolve(flag_key, default_value, int, evaluation_context)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[float]:
        return self._resolve(flag_key, default_value, float, evaluation_context)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType],
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[
        Sequence[FlagValueType] | Mapping[str, FlagValueType]
    ]:
        return self._resolve(flag_key, default_value, None, evaluation_context)

    @staticmethod
    def _unwrap_value(value: typing.Any) -> typing.Any:
        if isinstance(value, dict):
            return {k: MixpanelProvider._unwrap_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [MixpanelProvider._unwrap_value(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    @staticmethod
    def _build_user_context(
        evaluation_context: EvaluationContext | None,
    ) -> dict:
        user_context: dict = {}
        if evaluation_context is not None:
            if evaluation_context.attributes:
                for k, v in evaluation_context.attributes.items():
                    user_context[k] = MixpanelProvider._unwrap_value(v)
            if evaluation_context.targeting_key:
                user_context["targetingKey"] = evaluation_context.targeting_key
        return user_context

    def _resolve(
        self,
        flag_key: str,
        default_value: typing.Any,
        expected_type: type | None,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails:
        if not self._are_flags_ready():
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.PROVIDER_NOT_READY,
                reason=Reason.ERROR,
            )

        fallback = SelectedVariant(variant_value=default_value)
        user_context = self._build_user_context(evaluation_context)
        try:
            result = self._flags_provider.get_variant(flag_key, fallback, user_context)
        except Exception as exc:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.GENERAL,
                error_message=str(exc),
                reason=Reason.ERROR,
            )

        fallback_details = self._fallback_details(
            result.fallback_reason, default_value
        )
        if fallback_details is not None:
            return fallback_details

        value = result.variant_value
        variant_key = result.variant_key

        if expected_type is None:
            return FlagResolutionDetails(
                value=value, variant=variant_key, reason=Reason.TARGETING_MATCH
            )

        # In Python, bool is a subclass of int, so isinstance(True, int)
        # returns True. Reject bools early when expecting numeric types.
        if expected_type in (int, float) and isinstance(value, bool):
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.TYPE_MISMATCH,
                error_message=f"Expected {expected_type.__name__}, got {type(value).__name__}",
                reason=Reason.ERROR,
            )

        if expected_type is int and isinstance(value, float):
            if math.isfinite(value) and value == math.floor(value):
                return FlagResolutionDetails(
                    value=int(value), variant=variant_key, reason=Reason.TARGETING_MATCH
                )
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.TYPE_MISMATCH,
                error_message=f"Expected int, got float (value={value} is not a whole number)",
                reason=Reason.ERROR,
            )

        if expected_type is float and isinstance(value, (int, float)):
            return FlagResolutionDetails(
                value=float(value), variant=variant_key, reason=Reason.TARGETING_MATCH
            )

        if not isinstance(value, expected_type):
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.TYPE_MISMATCH,
                error_message=f"Expected {expected_type.__name__}, got {type(value).__name__}",
                reason=Reason.ERROR,
            )

        return FlagResolutionDetails(
            value=value, variant=variant_key, reason=Reason.TARGETING_MATCH
        )

    @staticmethod
    def _fallback_details(
        fallback_reason: FallbackReason | None, default_value: typing.Any
    ) -> FlagResolutionDetails | None:
        """Map a fallback reason to its OpenFeature response, or None if not a fallback.

        variant_source distinguishes local / remote / fallback. When fallback,
        fallback_reason carries the discriminating kind (PHP-aligned) and an
        optional message (BACKEND_ERROR's response body, MISSING_CONTEXT_KEY's
        missing attribute) so we map each to the spec-correct OpenFeature
        response and forward the message as error_message.
        """
        if fallback_reason is None:
            return None
        # Flag exists, user just didn't match any rollout — per the
        # OpenFeature spec this is `reason: DEFAULT` with no error.
        if fallback_reason.kind == "NO_ROLLOUT_MATCH":
            return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)
        # PROVIDER_NOT_READY is handled before invoking the provider
        # (see _are_flags_ready short-circuit at the top of resolve), so
        # there's no NOT_READY kind to dispatch on here.
        error_mapping = {
            "FLAG_NOT_FOUND": (ErrorCode.FLAG_NOT_FOUND, Reason.DEFAULT),
            "MISSING_CONTEXT_KEY": (ErrorCode.TARGETING_KEY_MISSING, Reason.ERROR),
            "BACKEND_ERROR": (ErrorCode.GENERAL, Reason.ERROR),
        }
        if fallback_reason.kind in error_mapping:
            error_code, reason = error_mapping[fallback_reason.kind]
            return FlagResolutionDetails(
                value=default_value,
                error_code=error_code,
                error_message=fallback_reason.message,
                reason=reason,
            )
        return None

    def _are_flags_ready(self) -> bool:
        if hasattr(self._flags_provider, "are_flags_ready"):
            return self._flags_provider.are_flags_ready()
        return True
