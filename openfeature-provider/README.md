# Mixpanel Python OpenFeature Provider

[![PyPI](https://img.shields.io/pypi/v/mixpanel-openfeature.svg)](https://pypi.org/project/mixpanel-openfeature/)
[![OpenFeature](https://img.shields.io/badge/OpenFeature-compatible-green)](https://openfeature.dev/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://github.com/mixpanel/mixpanel-python/blob/master/LICENSE)

An [OpenFeature](https://openfeature.dev/) provider that integrates Mixpanel's feature flags with the OpenFeature Python SDK. This allows you to use Mixpanel's feature flagging capabilities through OpenFeature's standardized, vendor-agnostic API.

## Overview

This package provides a bridge between Mixpanel's native feature flags implementation and the OpenFeature specification. By using this provider, you can:

- Leverage Mixpanel's powerful feature flag and experimentation platform
- Use OpenFeature's standardized API for flag evaluation
- Easily switch between feature flag providers without changing your application code
- Integrate with OpenFeature's ecosystem of tools and frameworks

## Installation

```bash
pip install mixpanel-openfeature
```

You will also need the OpenFeature Python SDK:

```bash
pip install openfeature-sdk
```

## Quick Start

```python
from mixpanel_openfeature import MixpanelProvider
from mixpanel.flags.types import LocalFlagsConfig
from openfeature import api

# 1. Create and register the provider with local evaluation
provider = MixpanelProvider.from_local_config(
    "YOUR_PROJECT_TOKEN",
    LocalFlagsConfig(token="YOUR_PROJECT_TOKEN"),
)
api.set_provider(provider)

# 2. Get a client and evaluate flags
client = api.get_client()
show_new_feature = client.get_boolean_value("new-feature-flag", False)

if show_new_feature:
    print("New feature is enabled!")
```

## Initialization

The provider supports three initialization methods depending on your evaluation strategy:

### Local Evaluation

Evaluates flags locally using cached flag definitions that are polled from Mixpanel. This is the recommended approach for most server-side applications as it minimizes latency.

```python
from mixpanel_openfeature import MixpanelProvider
from mixpanel.flags.types import LocalFlagsConfig

provider = MixpanelProvider.from_local_config(
    "YOUR_PROJECT_TOKEN",
    LocalFlagsConfig(token="YOUR_PROJECT_TOKEN"),
)
```

This automatically starts polling for flag definitions in the background.

### Remote Evaluation

Evaluates flags by making a request to Mixpanel's servers for each evaluation. Use this when you need real-time flag values and can tolerate the additional network latency.

```python
from mixpanel_openfeature import MixpanelProvider
from mixpanel.flags.types import RemoteFlagsConfig

provider = MixpanelProvider.from_remote_config(
    "YOUR_PROJECT_TOKEN",
    RemoteFlagsConfig(token="YOUR_PROJECT_TOKEN"),
)
```

### Using an Existing Mixpanel Instance

If your application already has a `Mixpanel` instance configured, you can create the provider from its flags provider directly rather than having the provider create a new one:

```python
from mixpanel import Mixpanel
from mixpanel.flags.types import LocalFlagsConfig
from mixpanel_openfeature import MixpanelProvider

# Your existing Mixpanel instance
mp = Mixpanel("YOUR_PROJECT_TOKEN", local_flags_config=LocalFlagsConfig(token="YOUR_PROJECT_TOKEN"))
local_flags = mp.local_flags
local_flags.start_polling_for_definitions()

# Wrap the existing flags provider with OpenFeature
provider = MixpanelProvider(local_flags)
```

> **Note:** When using this constructor, `provider.mixpanel` will return `None` since the provider does not own the `Mixpanel` instance.

## Usage Examples

### Basic Boolean Flag

```python
client = api.get_client()

# Get a boolean flag with a default value
is_feature_enabled = client.get_boolean_value("my-feature", False)

if is_feature_enabled:
    # Show the new feature
    pass
```

### Mixpanel Flag Types and OpenFeature Evaluation Methods

Mixpanel feature flags support three flag types. Use the corresponding OpenFeature evaluation method based on your flag's variant values:

| Mixpanel Flag Type | Variant Values | OpenFeature Method |
|---|---|---|
| Feature Gate | `True` / `False` | `get_boolean_value()` |
| Experiment | boolean, string, number, or JSON object | `get_boolean_value()`, `get_string_value()`, `get_integer_value()`, `get_float_value()`, or `get_object_value()` |
| Dynamic Config | JSON object | `get_object_value()` |

```python
client = api.get_client()

# Feature Gate - boolean variants
is_feature_on = client.get_boolean_value("new-checkout", False)

# Experiment with string variants
button_color = client.get_string_value("button-color-test", "blue")

# Experiment with integer variants
max_items = client.get_integer_value("max-items", 10)

# Experiment with float variants
threshold = client.get_float_value("score-threshold", 0.5)

# Dynamic Config - JSON object variants
feature_config = client.get_object_value("homepage-layout", {"layout": "default"})
```

### Getting Full Resolution Details

If you need additional metadata about the flag evaluation:

```python
client = api.get_client()

details = client.get_boolean_details("my-feature", False)

print(details.value)        # The resolved value
print(details.variant)      # The variant key from Mixpanel
print(details.reason)       # Why this value was returned
print(details.error_code)   # Error code if evaluation failed
```

### Setting Context

You can pass evaluation context that will be sent to Mixpanel for flag evaluation:

```python
from openfeature.evaluation_context import EvaluationContext

context = EvaluationContext(
    targeting_key="user-123",
    attributes={
        "email": "user@example.com",
        "plan": "premium",
        "beta_tester": True,
    },
)

value = client.get_boolean_value("premium-feature", False, context)
```

### Accessing the Underlying Mixpanel Instance

If you initialized the provider with a token and config, you can access the underlying `Mixpanel` instance for sending events or profile updates:

```python
mp = provider.mixpanel
```

> **Note:** This returns `None` if the provider was constructed with a flags provider directly.

### Shutdown

When your application is shutting down, call `shutdown()` to clean up resources:

```python
provider.shutdown()
```

## Context Mapping

### All Properties Passed Directly

All properties in the OpenFeature `EvaluationContext` are passed directly to Mixpanel's feature flag evaluation. There is no transformation or filtering of properties.

```python
# This OpenFeature context...
context = EvaluationContext(
    targeting_key="user-123",
    attributes={
        "email": "user@example.com",
        "plan": "premium",
    },
)

# ...is passed to Mixpanel as-is for flag evaluation
```

### targetingKey is Not Special

Unlike some feature flag providers, `targetingKey` is **not** used as a special bucketing key in Mixpanel. It is simply passed as another context property. Mixpanel's server-side configuration determines which properties are used for targeting rules and bucketing.

## Error Handling

The provider uses OpenFeature's standard error codes to indicate issues during flag evaluation:

### PROVIDER_NOT_READY

Returned when flags are evaluated before the local flags provider has finished loading flag definitions. This only applies when using local evaluation.

```python
details = client.get_boolean_details("my-feature", False)

if details.error_code == ErrorCode.PROVIDER_NOT_READY:
    print("Provider still loading, using default value")
```

### FLAG_NOT_FOUND

Returned when the requested flag does not exist in Mixpanel.

```python
details = client.get_boolean_details("nonexistent-flag", False)

if details.error_code == ErrorCode.FLAG_NOT_FOUND:
    print("Flag does not exist, using default value")
```

### TYPE_MISMATCH

Returned when the flag value type does not match the requested type. The provider supports some numeric coercions (e.g., a whole-number `float` flag value can be retrieved via `get_integer_value()`, and any numeric type can be retrieved via `get_float_value()`), but incompatible types will return this error.

```python
# If 'my-flag' is configured as a string in Mixpanel...
details = client.get_boolean_details("my-flag", False)

if details.error_code == ErrorCode.TYPE_MISMATCH:
    print("Flag is not a boolean, using default value")
```

## Troubleshooting

### Flags Always Return Default Values

**Possible causes:**

1. **Provider not ready (local evaluation):** The local flags provider may still be loading flag definitions. Flag definitions are polled asynchronously after the provider is created. Allow time for the initial fetch to complete, or check the `PROVIDER_NOT_READY` error code.

2. **Invalid project token:** Verify the token passed to the config matches your Mixpanel project.

3. **Flag not configured:** Verify the flag exists in your Mixpanel project and is enabled.

4. **Network issues:** Check that your application can reach Mixpanel's API servers.

### Type Mismatch Errors

If you are getting `TYPE_MISMATCH` errors:

1. **Check flag configuration:** Verify the flag's value type in Mixpanel matches how you are evaluating it. For example, if the flag value is the string `"true"`, use `get_string_value()`, not `get_boolean_value()`.

2. **Use `get_object_value()` for complex types:** For JSON objects or arrays, use `get_object_value()`.

3. **Numeric coercion:** Integer evaluation accepts whole-number `float` values. Float evaluation accepts any numeric type (`int` or `float`).

### Exposure Events Not Tracking

If `$experiment_started` events are not appearing in Mixpanel:

1. **Verify Mixpanel tracking is working:** Test that other Mixpanel events are being tracked successfully.

2. **Check for duplicate evaluations:** Mixpanel only tracks the first exposure per flag per session to avoid duplicate events.

## Requirements

- Python 3.9 or higher
- `mixpanel` 5.1.0+
- `openfeature-sdk` 0.7.0+

## License

Apache-2.0
