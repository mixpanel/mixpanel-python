# Changelog

## [v5.2.0](https://github.com/mixpanel/mixpanel-python/tree/v5.2.0) (2026-07-10)

### Features
- add service account authentication support ([#175](https://github.com/mixpanel/mixpanel-python/pull/175))

### Fixes
- restore PyPy 3.9 compatibility by pinning pydantic ([#176](https://github.com/mixpanel/mixpanel-python/pull/176))

[Full Changelog](https://github.com/mixpanel/mixpanel-python/compare/v5.1.0...v5.2.0)

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class for enhanced security in server-to-server integrations. Service accounts use HTTP Basic Authentication with username/secret/project_id instead of shared API secrets (api_key/api_secret). All three parameters are required and validated (non-empty, non-whitespace).
- `credentials` parameter added to `Mixpanel`, `Consumer`, `BufferedConsumer`, `LocalFeatureFlagsProvider`, and `RemoteFeatureFlagsProvider` constructors to accept `ServiceAccountCredentials`.
- When service account credentials are provided:
  - Feature flag endpoints (`/flags`, `/flags/definitions`) authenticate with BasicAuth header and include `project_id` as a query parameter instead of `token`
  - Import endpoint (`/import`) authenticates with BasicAuth header, includes `project_id` as a query parameter, and does NOT include `api_key` in the POST body
  - Service account credentials take precedence over API secrets when both are provided

### Changed
- `Consumer` and `BufferedConsumer` now accept service account credentials in their constructors. Credentials are configured once at construction time rather than being passed on every `send()` call, providing cleaner architecture and better encapsulation.
- `Consumer._write_request()` internally checks `self._credentials` and the endpoint to determine whether to use service account authentication, conditionally including `api_key` in POST body only when using legacy API secret authentication (not when using service account credentials)
- `Mixpanel()` constructor now emits a `UserWarning` when both `consumer` and `credentials` parameters are provided. When a custom consumer is supplied, credentials passed to `Mixpanel()` are ignored - they must be passed to the consumer's constructor instead to take effect. This warning helps prevent silent authentication failures.

### Deprecated
- `api_key` and `api_secret` parameters are deprecated in favor of `ServiceAccountCredentials`. Logger warnings now alert users when using legacy authentication methods. These parameters will be removed in a future major version.

### Fixed
- Service account credentials are now only applied to the `/import` endpoint (and feature flag endpoints). Previously, credentials were incorrectly passed to `/track`, `/engage`, and `/groups` endpoints, which could cause request rejection or silent event loss. The fix ensures `track()`, `alias()`, `people_update()`, and `group_update()` no longer include service account authentication headers, while `import_data()` and `merge()` continue to work correctly with credentials.
- Remote feature flags no longer double-encode the `context` query parameter. Previously, the library manually URL-encoded the context JSON before passing it to `httpx`, which would then encode it again, resulting in double-encoded values being sent to the Mixpanel API. Now `httpx` handles all URL encoding automatically.
