from typing import Optional, List, Dict, Any
from pydantic import BaseModel

MIXPANEL_DEFAULT_API_ENDPOINT = "api.mixpanel.com"
class FlagsConfig(BaseModel):
    api_host: str = "api.mixpanel.com"
    requestTimeoutInSeconds: int = 10
    retryLimit: int = 3
    retryExponentialBackoffFactor: int = 1

class LocalFlagsConfig(FlagsConfig):
    enablePolling: bool = True
    pollingIntervalInSeconds: int = 60

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
    runtime_evaluation_definition: Optional[Dict[str, Any]] = None
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
    variant_value: str

class ExperimentationFlags(BaseModel):
    flags: List[ExperimentationFlag] 

class RemoteFlagsResponse(BaseModel):
    code: int
    flags: Dict[str, SelectedVariant]