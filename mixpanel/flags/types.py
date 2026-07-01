from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

MIXPANEL_DEFAULT_API_ENDPOINT = "api.mixpanel.com"


class FlagsConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_host: str = "api.mixpanel.com"
    request_timeout_in_seconds: int = 10


class LocalFlagsConfig(FlagsConfig):
    enable_polling: bool = True
    polling_interval_in_seconds: int = 60


class RemoteFlagsConfig(FlagsConfig):
    pass


class Variant(BaseModel):
    key: str
    value: Any
    is_control: bool
    split: Optional[float] = 0.0


class FlagTestUsers(BaseModel):
    users: dict[str, str]


class VariantOverride(BaseModel):
    key: str


class Rollout(BaseModel):
    rollout_percentage: float
    runtime_evaluation_definition: Optional[dict[str, str]] = None
    runtime_evaluation_rule: Optional[dict[Any, Any]] = None
    variant_override: Optional[VariantOverride] = None
    variant_splits: Optional[dict[str, float]] = None


class RuleSet(BaseModel):
    variants: list[Variant]
    rollout: list[Rollout]
    test: Optional[FlagTestUsers] = None


class ExperimentationFlag(BaseModel):
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


class VariantSource:
    """Where a SelectedVariant came from.

    Set by the providers on every returned variant — coarse-grained
    (local / remote / fallback). For the specific reason behind a fallback,
    see FallbackReason.
    """

    LOCAL = "local"
    REMOTE = "remote"
    FALLBACK = "fallback"


class FallbackReason(BaseModel):
    """Why the SDK returned the developer fallback.

    Only meaningful when SelectedVariant.variant_source == VariantSource.FALLBACK.

    `kind` is the discriminator (PHP-aligned). `message` is set on reasons
    that carry useful detail (BACKEND_ERROR with the backend's response body,
    MISSING_CONTEXT_KEY with the missing attribute name); None otherwise.
    The OpenFeature wrapper dispatches on kind and forwards message into
    FlagResolutionDetails.error_message.
    """

    model_config = ConfigDict(frozen=True)

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


class SelectedVariant(BaseModel):
    # variant_key can be None if being used as a fallback
    variant_key: Optional[str] = None
    variant_value: Any
    experiment_id: Optional[str] = None
    is_experiment_active: Optional[bool] = None
    is_qa_tester: Optional[bool] = None
    variant_source: Optional[str] = None
    # None on success; set when variant_source == FALLBACK
    fallback_reason: Optional[FallbackReason] = None

    def with_source(self, source: str) -> "SelectedVariant":
        """Return a copy of this variant tagged with the given source.

        Clears fallback_reason — use as_fallback() if returning a fallback.
        """
        return self.model_copy(
            update={"variant_source": source, "fallback_reason": None}
        )

    def as_fallback(self, reason: FallbackReason) -> "SelectedVariant":
        """Return a copy of this variant tagged as a fallback with the given reason."""
        return self.model_copy(
            update={
                "variant_source": VariantSource.FALLBACK,
                "fallback_reason": reason,
            }
        )


class ExperimentationFlags(BaseModel):
    flags: list[ExperimentationFlag]


class RemoteFlagsResponse(BaseModel):
    code: int
    flags: dict[str, SelectedVariant]
