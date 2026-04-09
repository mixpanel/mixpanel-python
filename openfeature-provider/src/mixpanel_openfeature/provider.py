from __future__ import annotations

import math
import typing
from collections.abc import Mapping, Sequence
from typing import Optional, Union

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata

from mixpanel import Mixpanel
from mixpanel.flags.types import LocalFlagsConfig, RemoteFlagsConfig, SelectedVariant

FlagValueType = Union[bool, str, int, float, list, dict, None]


class MixpanelProvider(AbstractProvider):
    """An OpenFeature provider backed by a Mixpanel feature flags provider."""

    def __init__(
        self,
        flags_provider: typing.Any,
        mixpanel_instance: Optional[Mixpanel] = None,
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
    def mixpanel(self) -> Optional[Mixpanel]:
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
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[bool]:
        return self._resolve(flag_key, default_value, bool, evaluation_context)

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[str]:
        return self._resolve(flag_key, default_value, str, evaluation_context)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[int]:
        return self._resolve(flag_key, default_value, int, evaluation_context)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[float]:
        return self._resolve(flag_key, default_value, float, evaluation_context)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Union[Sequence[FlagValueType], Mapping[str, FlagValueType]],
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[
        Union[Sequence[FlagValueType], Mapping[str, FlagValueType]]
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
        evaluation_context: typing.Optional[EvaluationContext],
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
        expected_type: typing.Optional[type],
        evaluation_context: typing.Optional[EvaluationContext] = None,
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
        except Exception:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.GENERAL,
                reason=Reason.ERROR,
            )

        if result is fallback:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.FLAG_NOT_FOUND,
                reason=Reason.DEFAULT,
            )

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

    def _are_flags_ready(self) -> bool:
        if hasattr(self._flags_provider, "are_flags_ready"):
            return self._flags_provider.are_flags_ready()
        return True
