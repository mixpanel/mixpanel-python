from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, ConfigDict

MIXPANEL_DEFAULT_API_ENDPOINT = "api.mixpanel.com"

class FlagsConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_host: str = "api.mixpanel.com"
    request_timeout_in_seconds: int = 10
    retry_limit: int = 3
    retry_exponential_backoff_factor: int = 1
    custom_executor: Optional[ThreadPoolExecutor] = None

class LocalFlagsConfig(FlagsConfig):
    enable_polling: bool = True
    polling_interval_in_seconds: int = 60

class RemoteFlagsConfig(FlagsConfig):
    pass

class Variant(BaseModel):
    key: str
    value: str
    is_control: bool
    split: float

class FlagTestUsers(BaseModel):
    users: Dict[str, str]

class VariantOverride(BaseModel):
    key: str

class Rollout(BaseModel):
    rollout_percentage: float
    runtime_evaluation_definition: Optional[Dict[str, str]] = None
    variant_override: Optional[VariantOverride] = None

class RuleSet(BaseModel):
    variants: List[Variant]
    rollout: List[Rollout]
    test: Optional[FlagTestUsers] = None

class ExperimentationFlag(BaseModel):
    id: str
    name: str
    key: str 
    status: str
    project_id: int
    ruleset: RuleSet 
    context: str

class SelectedVariant(BaseModel):
    variant_key: str
    variant_value: Any

class ExperimentationFlags(BaseModel):
    flags: List[ExperimentationFlag] 

class RemoteFlagsResponse(BaseModel):
    code: int
    flags: Dict[str, SelectedVariant]