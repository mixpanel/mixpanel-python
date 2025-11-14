# Copilot Instructions for Mixpanel Python SDK

## Project Overview
This is the official Mixpanel Python library for server-side analytics integration. It provides event tracking, user profile updates, group analytics, and feature flags with both synchronous and asynchronous support.

## Core Architecture

### Main Components
- **Mixpanel class** (`mixpanel/__init__.py`): Primary entry point supporting both sync/async operations
- **Consumer pattern**: `Consumer` (immediate) vs `BufferedConsumer` (batched, default 50 messages)
- **Feature Flags**: Local (client-side evaluation) vs Remote (server-side) providers in `mixpanel/flags/`
- **Dual sync/async API**: Most flag operations have both variants (e.g., `get_variant`/`aget_variant`)

### Key Design Patterns
```python
# Context manager pattern for resource cleanup
async with Mixpanel(token, local_flags_config=config) as mp:
    await mp.local_flags.astart_polling_for_definitions()

# Consumer customization for delivery behavior
mp = Mixpanel(token, consumer=BufferedConsumer())

# Custom serialization via DatetimeSerializer
mp = Mixpanel(token, serializer=CustomSerializer)
```

## Development Workflows

### Testing
- **Run tests**: `pytest` (current Python) or `python -m tox` (all supported versions 3.9-3.13)
- **Async testing**: Uses `pytest-asyncio` with `asyncio_mode = "auto"` in pyproject.toml
- **HTTP mocking**: `responses` library for sync code, `respx` for async code
- **Test structure**: `test_*.py` files in root and package directories

### Building & Publishing
```bash
pip install -e .[test,dev]  # Development setup
python -m build            # Build distributions
python -m twine upload dist/*  # Publish to PyPI
```

## Important Conventions

### API Endpoints & Authentication
- Default endpoint: `api.mixpanel.com` (override via `api_host` parameter)
- **API secret** (not key) required for `import` and `merge` endpoints
- Feature flags use `/decide` endpoint; events use `/track`

### Error Handling & Retries
- All consumers use urllib3.Retry with exponential backoff (default 4 retries)
- `MixpanelException` for domain-specific errors
- Feature flag operations degrade gracefully with fallback values

### Version & Dependencies Management
- Version defined in `mixpanel/__init__.py` as `__version__`
- Uses Pydantic v2+ for data validation (`mixpanel/flags/types.py`)
- json-logic library for runtime flag evaluation rules

## Feature Flag Specifics

### Local Flags (Client-side evaluation)
- Require explicit polling: `start_polling_for_definitions()` or context manager
- Default 60s polling interval, configurable via `LocalFlagsConfig`
- Runtime evaluation using json-logic for dynamic targeting

### Remote Flags (Server-side evaluation)
- Each evaluation makes API call to Mixpanel
- Better for sensitive targeting logic
- Configure via `RemoteFlagsConfig`

### Flag Configuration Pattern
```python
local_config = mixpanel.LocalFlagsConfig(
    api_host="api-eu.mixpanel.com",  # EU data residency
    enable_polling=True,
    polling_interval_in_seconds=90
)
mp = Mixpanel(token, local_flags_config=local_config)
```

## Testing Patterns
- Mock HTTP with `responses.activate` decorator for sync tests
- Use `respx.mock` for async HTTP testing
- Test consumer behavior via `LogConsumer` pattern (see `test_mixpanel.py`)
- Always test both sync and async variants of flag operations

## Critical Implementation Notes
- `alias()` method always uses synchronous Consumer regardless of main consumer type
- Local flags require explicit startup; use context managers for proper cleanup
- DateTime serialization handled by `DatetimeSerializer` class
- All flag providers support custom API endpoints for data residency requirements