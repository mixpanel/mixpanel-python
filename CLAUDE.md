# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the official Mixpanel Python library for server-side integration. It provides event tracking, user profile updates, group analytics, and feature flags functionality. The library supports both synchronous and asynchronous operations.

## Development Commands

### Environment Setup
```bash
# Install development and test dependencies
pip install -e .[test,dev]
```

### Testing
```bash
# Run all tests across all Python versions (3.9-3.13, PyPy)
python -m tox

# Run tests for current Python version only
pytest

# Run with coverage
python -m coverage run -m pytest
python -m coverage report -m
python -m coverage html

# Run specific test file
pytest test_mixpanel.py
pytest mixpanel/flags/test_local_feature_flags.py
```

### Building and Publishing
```bash
# Build distribution packages
python -m build

# Publish to PyPI
python -m twine upload dist/*
```

### Documentation
```bash
# Build documentation
python -m sphinx -b html docs docs/_build/html

# Publish docs to GitHub Pages
python -m ghp_import -n -p docs/_build/html
```

## Architecture

### Core Components

**Mixpanel Class** (`mixpanel/__init__.py`)
- Main entry point for all tracking operations
- Supports context managers (both sync and async)
- Integrates with Consumer classes for message delivery
- Optional feature flags providers (local and remote)

**Consumers**
- `Consumer`: Sends HTTP requests immediately (one per call)
- `BufferedConsumer`: Batches messages (default max 50) before sending
- Both support retry logic (default 4 retries with exponential backoff)
- All consumers support custom API endpoints via `api_host` parameter

**Feature Flags** (`mixpanel/flags/`)
- `LocalFeatureFlagsProvider`: Client-side evaluation with polling (default 60s interval)
- `RemoteFeatureFlagsProvider`: Server-side evaluation via API calls
- Both providers support async operations
- Types defined in `mixpanel/flags/types.py` using Pydantic models

### Key Design Patterns

1. **Dual Sync/Async Support**: Most feature flag operations have both sync and async variants (e.g., `get_variant` / `aget_variant`)

2. **Consumer Pattern**: Events/updates are sent via consumer objects, allowing customization of delivery behavior without changing tracking code

3. **Context Managers**: The Mixpanel class supports both `with` and `async with` patterns to manage flag provider lifecycle

4. **JSON Serialization**: Custom `DatetimeSerializer` handles datetime objects; extensible via `serializer` parameter

5. **Runtime Rules Engine**: Local flags support runtime evaluation using json-logic library for dynamic targeting

## Testing Patterns

- Tests use `pytest` with `pytest-asyncio` for async support
- `responses` library mocks HTTP requests for sync code
- `respx` library mocks HTTP requests for async code
- Test files follow pattern: `test_*.py` in root or within package directories
- Pytest config: `asyncio_mode = "auto"` in pyproject.toml

## Dependencies

- `requests>=2.4.2, <3`: HTTP client (sync)
- `httpx>=0.27.0`: HTTP client (async)
- `pydantic>=2.0.0`: Data validation and types
- `asgiref>=3.0.0`: Async utilities
- `json-logic>=0.7.0a0`: Runtime rules evaluation

## Version Management

Version is defined in `mixpanel/__init__.py` as `__version__` and dynamically loaded by setuptools.

## API Endpoints

Default: `api.mixpanel.com`
- Events: `/track`
- People: `/engage`
- Groups: `/groups`
- Imports: `/import`
- Feature Flags: `/decide`

## Important Notes

- API secret (not API key) is required for `import` and `merge` endpoints
- `alias()` always uses synchronous Consumer regardless of main consumer type
- Feature flags require opt-in via constructor config parameters
- Local flags poll for updates; call `start_polling_for_definitions()` or use context manager
- Retry logic uses urllib3.Retry with exponential backoff
