import math
import typing
from typing import Mapping, Sequence, Union

from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata

from mixpanel.flags.types import SelectedVariant

FlagValueType = Union[bool, str, int, float, list, dict, None]


class MixpanelProvider(AbstractProvider):
    """An OpenFeature provider backed by a Mixpanel feature flags provider."""

    def __init__(self, flags_provider: typing.Any) -> None:
        super().__init__()
        self._flags_provider = flags_provider

    def get_metadata(self) -> Metadata:
        return Metadata(name="mixpanel-provider")

    def shutdown(self) -> None:
        pass

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[bool]:
        return self._resolve(flag_key, default_value, bool)

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[str]:
        return self._resolve(flag_key, default_value, str)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[int]:
        return self._resolve(flag_key, default_value, int)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[float]:
        return self._resolve(flag_key, default_value, float)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Union[Sequence[FlagValueType], Mapping[str, FlagValueType]],
        evaluation_context: typing.Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[
        Union[Sequence[FlagValueType], Mapping[str, FlagValueType]]
    ]:
        return self._resolve(flag_key, default_value, None)

    def _resolve(
        self,
        flag_key: str,
        default_value: typing.Any,
        expected_type: typing.Optional[type],
    ) -> FlagResolutionDetails:
        if not self._are_flags_ready():
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.PROVIDER_NOT_READY,
                reason=Reason.ERROR,
            )

        fallback = SelectedVariant(variant_value=default_value)
        result = self._flags_provider.get_variant(flag_key, fallback, {})

        if result is fallback:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.FLAG_NOT_FOUND,
                reason=Reason.ERROR,
            )

        value = result.variant_value

        if expected_type is None:
            return FlagResolutionDetails(value=value, reason=Reason.STATIC)

        if expected_type is int and isinstance(value, float):
            if math.isfinite(value) and value == math.floor(value):
                return FlagResolutionDetails(
                    value=int(value), reason=Reason.STATIC
                )
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.TYPE_MISMATCH,
                reason=Reason.ERROR,
            )

        if expected_type is float and isinstance(value, (int, float)):
            return FlagResolutionDetails(
                value=float(value), reason=Reason.STATIC
            )

        if not isinstance(value, expected_type):
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.TYPE_MISMATCH,
                reason=Reason.ERROR,
            )

        return FlagResolutionDetails(value=value, reason=Reason.STATIC)

    def _are_flags_ready(self) -> bool:
        if hasattr(self._flags_provider, "are_flags_ready"):
            return self._flags_provider.are_flags_ready()
        return True
