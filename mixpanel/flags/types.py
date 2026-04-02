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


class SelectedVariant(BaseModel):
    # variant_key can be None if being used as a fallback
    variant_key: Optional[str] = None
    variant_value: Any
    experiment_id: Optional[str] = None
    is_experiment_active: Optional[bool] = None
    is_qa_tester: Optional[bool] = None


class ExperimentationFlags(BaseModel):
    flags: list[ExperimentationFlag]


class RemoteFlagsResponse(BaseModel):
    code: int
    flags: dict[str, SelectedVariant]
