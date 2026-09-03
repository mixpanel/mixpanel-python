from concurrent.futures import Executor
from dataclasses import dataclass, fields, replace
from typing import Any, Literal, Optional, TypeVar

MIXPANEL_DEFAULT_API_ENDPOINT = "api.mixpanel.com"

_Dataclass = TypeVar("_Dataclass")


def _from_payload(
    cls: type[_Dataclass], payload: dict[str, Any], **parsed_fields: Any
) -> _Dataclass:
    """Build a dataclass from an API payload.

    Keys the dataclass does not declare are ignored so that new fields added
    to the API response never break older SDK versions. Missing required
    fields raise TypeError from the dataclass constructor. ``parsed_fields``
    override raw payload values for fields that hold nested models.
    """
    declared_fields = {field.name for field in fields(cls)}  # type: ignore[arg-type]
    kwargs = {key: value for key, value in payload.items() if key in declared_fields}
    kwargs.update(parsed_fields)
    return cls(**kwargs)


@dataclass
class FlagsConfig:
    api_host: str = "api.mixpanel.com"
    request_timeout_in_seconds: int = 10
    # Optional executor used to dispatch exposure-event HTTP sends so flag
    # evaluation does not block on the network round trip. None (default)
    # preserves the existing inline behavior.
    exposure_executor: Optional[Executor] = None
    # Scheme used to reach api_host. True (default) uses https. Set to False
    # only to reach a local/dev endpoint served over plain HTTP (e.g. a development
    # nginx proxy), which avoids needing a TLS cert the client can verify.
    use_https: bool = True


@dataclass
class LocalFlagsConfig(FlagsConfig):
    enable_polling: bool = True
    polling_interval_in_seconds: int = 60


@dataclass
class RemoteFlagsConfig(FlagsConfig):
    pass


@dataclass
class Variant:
    key: str
    value: Any
    is_control: bool
    split: Optional[float] = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Variant":
        return _from_payload(cls, payload)


@dataclass
class FlagTestUsers:
    users: dict[str, str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FlagTestUsers":
        return _from_payload(cls, payload)


@dataclass
class VariantOverride:
    key: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VariantOverride":
        return _from_payload(cls, payload)


@dataclass
class Rollout:
    rollout_percentage: float
    runtime_evaluation_definition: Optional[dict[str, str]] = None
    runtime_evaluation_rule: Optional[dict[Any, Any]] = None
    variant_override: Optional[VariantOverride] = None
    variant_splits: Optional[dict[str, float]] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Rollout":
        variant_override = payload.get("variant_override")
        return _from_payload(
            cls,
            payload,
            variant_override=(
                VariantOverride.from_dict(variant_override)
                if variant_override is not None
                else None
            ),
        )


@dataclass
class RuleSet:
    variants: list[Variant]
    rollout: list[Rollout]
    test: Optional[FlagTestUsers] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuleSet":
        test_users = payload.get("test")
        return _from_payload(
            cls,
            payload,
            variants=[Variant.from_dict(variant) for variant in payload["variants"]],
            rollout=[Rollout.from_dict(rollout) for rollout in payload["rollout"]],
            test=(
                FlagTestUsers.from_dict(test_users) if test_users is not None else None
            ),
        )


@dataclass
class ExperimentationFlag:
    id: str
    name: str
    key: str
    status: str
    project_id: int
    ruleset: RuleSet
    context: str
    experiment_id: Optional[str] = None
    is_experiment_active: Optional[bool] = None
    hash_salt: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExperimentationFlag":
        return _from_payload(
            cls, payload, ruleset=RuleSet.from_dict(payload["ruleset"])
        )


class VariantSource:
    """Where a SelectedVariant came from.

    Set by the providers on every returned variant — coarse-grained
    (local / remote / fallback). For the specific reason behind a fallback,
    see FallbackReason.
    """

    LOCAL = "local"
    REMOTE = "remote"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class FallbackReason:
    """Why the SDK returned the developer fallback.

    Only meaningful when SelectedVariant.variant_source == VariantSource.FALLBACK.

    `kind` is the discriminator (PHP-aligned). `message` is set on reasons
    that carry useful detail (BACKEND_ERROR with the backend's response body,
    MISSING_CONTEXT_KEY with the missing attribute name); None otherwise.
    The OpenFeature wrapper dispatches on kind and forwards message into
    FlagResolutionDetails.error_message.
    """

    kind: Literal[
        "FLAG_NOT_FOUND",
        "MISSING_CONTEXT_KEY",
        "NO_ROLLOUT_MATCH",
        "BACKEND_ERROR",
    ]
    message: Optional[str] = None

    # Factory methods. Reasons without meaningful detail return a frozen
    # singleton; reasons with detail allocate per call.
    @classmethod
    def flag_not_found(cls) -> "FallbackReason":
        return _FLAG_NOT_FOUND

    @classmethod
    def no_rollout_match(cls) -> "FallbackReason":
        return _NO_ROLLOUT_MATCH

    @classmethod
    def missing_context_key(cls, key: str) -> "FallbackReason":
        # The whole point of MISSING_CONTEXT_KEY is telling the caller *which*
        # attribute is absent; a nullable default would leak `message=None`
        # into the OpenFeature wrapper's error_message and defeat the SDK-79
        # richer-error-propagation goal.
        return cls(kind="MISSING_CONTEXT_KEY", message=key)

    @classmethod
    def backend_error(cls, message: str) -> "FallbackReason":
        return cls(kind="BACKEND_ERROR", message=message)


_FLAG_NOT_FOUND = FallbackReason(kind="FLAG_NOT_FOUND")
_NO_ROLLOUT_MATCH = FallbackReason(kind="NO_ROLLOUT_MATCH")


@dataclass
class SelectedVariant:
    variant_value: Any
    # variant_key can be None if being used as a fallback
    variant_key: Optional[str] = None
    experiment_id: Optional[str] = None
    is_experiment_active: Optional[bool] = None
    is_qa_tester: Optional[bool] = None
    variant_source: Optional[str] = None
    # None on success; set when variant_source == FALLBACK
    fallback_reason: Optional[FallbackReason] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SelectedVariant":
        fallback_reason = payload.get("fallback_reason")
        return _from_payload(
            cls,
            payload,
            fallback_reason=(
                _from_payload(FallbackReason, fallback_reason)
                if fallback_reason is not None
                else None
            ),
        )

    def with_source(self, source: str) -> "SelectedVariant":
        """Return a copy of this variant tagged with the given source.

        Clears fallback_reason — use as_fallback() if returning a fallback.
        """
        return replace(self, variant_source=source, fallback_reason=None)

    def as_fallback(self, reason: FallbackReason) -> "SelectedVariant":
        """Return a copy of this variant tagged as a fallback with the given reason."""
        return replace(
            self, variant_source=VariantSource.FALLBACK, fallback_reason=reason
        )


@dataclass
class ExperimentationFlags:
    flags: list[ExperimentationFlag]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExperimentationFlags":
        return cls(
            flags=[ExperimentationFlag.from_dict(flag) for flag in payload["flags"]]
        )


@dataclass
class RemoteFlagsResponse:
    code: int
    flags: dict[str, SelectedVariant]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RemoteFlagsResponse":
        return cls(
            code=payload["code"],
            flags={
                flag_key: SelectedVariant.from_dict(variant)
                for flag_key, variant in payload["flags"].items()
            },
        )
