# Releasing the OpenFeature Provider

The OpenFeature provider (`mixpanel-openfeature`) is published to PyPI independently from the core SDK.

## Prerequisites

- Python 3.9+
- `build` and `twine` packages: `pip install build twine`
- A PyPI API token with permission to upload to the `mixpanel-openfeature` project
  - Create one at https://pypi.org/manage/account/token/
  - For the first upload, you'll need an account-scoped token (project-scoped tokens can only be created after the project exists on PyPI)

## Releasing

1. Update the version in `pyproject.toml`

2. Build the package:
   ```bash
   cd openfeature-provider
   python -m build
   ```

3. Verify the built artifacts look correct:
   ```bash
   ls dist/
   # Should show: mixpanel_openfeature-<version>-py3-none-any.whl
   #              mixpanel_openfeature-<version>.tar.gz
   ```

4. Upload to PyPI:
   ```bash
   python -m twine upload dist/*
   ```
   Twine will prompt for credentials. Use `__token__` as the username and your API token as the password. Alternatively, configure `~/.pypirc`:
   ```ini
   [pypi]
   username = __token__
   password = pypi-<your-token>
   ```

5. Verify at https://pypi.org/project/mixpanel-openfeature/

## Versioning

The OpenFeature provider is versioned independently from the core SDK. The core SDK dependency version is pinned in `pyproject.toml` (`mixpanel>=5.1.0,<6`) — update it when the provider needs features from a newer core SDK release.
