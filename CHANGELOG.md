# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class for enhanced security in server-to-server integrations. Service accounts use HTTP Basic Authentication with username/secret/project_id instead of shared API secrets (api_key/api_secret). All three parameters are required and validated (non-empty, non-whitespace).
- `credentials` parameter added to `Mixpanel`, `Consumer`, and `BufferedConsumer` constructors to accept `ServiceAccountCredentials`.
- When service account credentials are provided, they automatically apply to feature flag operations (`LocalFeatureFlagsProvider` and `RemoteFeatureFlagsProvider`).
- The `httpx_client_parameters` parameter is now optional in `LocalFeatureFlagsProvider` and `RemoteFeatureFlagsProvider` constructors. When not provided, defaults to basic authentication with the project token. This maintains backward compatibility with existing code that instantiates flag providers directly.
