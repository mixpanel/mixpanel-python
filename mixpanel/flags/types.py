from typing import Any, Optional

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
    """Where a SelectedVariant came from. Set by the providers on every
    returned variant — coarse-grained (local / remote / fallback). For the
    specific reason behind a fallback, see FallbackReason.
    """

    LOCAL = "local"
    REMOTE = "remote"
    FALLBACK = "fallback"


class FallbackReason:
    """Why the SDK returned the developer fallback. Only meaningful when
    SelectedVariant.variant_source == VariantSource.FALLBACK. Matches the
    constant set used by mixpanel-php so the OpenFeature wrapper can map to
    the spec-correct error code instead of collapsing every fallback to
    FLAG_NOT_FOUND.
    """

    FLAG_NOT_FOUND = "FLAG_NOT_FOUND"
    MISSING_CONTEXT_KEY = "MISSING_CONTEXT_KEY"
    NO_ROLLOUT_MATCH = "NO_ROLLOUT_MATCH"
    BACKEND_ERROR = "BACKEND_ERROR"
    NOT_READY = "NOT_READY"


class SelectedVariant(BaseModel):
    # variant_key can be None if being used as a fallback
    variant_key: Optional[str] = None
    variant_value: Any
    experiment_id: Optional[str] = None
    is_experiment_active: Optional[bool] = None
    is_qa_tester: Optional[bool] = None
    variant_source: Optional[str] = None
    # None on success; one of FallbackReason.* when variant_source is FALLBACK
    fallback_reason: Optional[str] = None

    def with_source(self, source: str) -> "SelectedVariant":
        """Return a copy of this variant tagged with the given source.
        Clears fallback_reason — use as_fallback() if returning a fallback.
        """
        return self.model_copy(
            update={"variant_source": source, "fallback_reason": None}
        )

    def as_fallback(self, reason: str) -> "SelectedVariant":
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
