# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class for enhanced security in server-to-server integrations. Service accounts use HTTP Basic Authentication with username/secret/project_id instead of shared API secrets (api_key/api_secret). All three parameters are required and validated (non-empty, non-whitespace).
- `credentials` parameter added to `Mixpanel`, `LocalFeatureFlagsProvider`, and `RemoteFeatureFlagsProvider` constructors to accept `ServiceAccountCredentials`.
- When service account credentials are provided:
  - Feature flag endpoints (`/flags`, `/flags/definitions`) authenticate with BasicAuth header and include `project_id` as a query parameter instead of `token`
  - Import endpoint (`/import`) authenticates with BasicAuth header, includes `project_id` as a query parameter, and does NOT include `api_key` in the POST body
  - Service account credentials take precedence over API secrets when both are provided

### Changed
- `Consumer._write_request()` now accepts service account credentials and conditionally includes `api_key` in POST body only when using legacy API secret authentication (not when using service account credentials)

### Deprecated
- `api_key` and `api_secret` parameters are deprecated in favor of `ServiceAccountCredentials`. Logger warnings now alert users when using legacy authentication methods. These parameters will be removed in a future major version.

### Fixed
- Remote feature flags no longer double-encode the `context` query parameter. Previously, the library manually URL-encoded the context JSON before passing it to `httpx`, which would then encode it again, resulting in double-encoded values being sent to the Mixpanel API. Now `httpx` handles all URL encoding automatically.
- `alias()` now correctly uses service account credentials when configured on the `Mixpanel` instance. Previously, it would create a new consumer without passing credentials, causing authentication to fail.
