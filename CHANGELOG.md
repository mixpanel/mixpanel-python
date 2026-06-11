# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class. Pass credentials to `Mixpanel`, `Consumer`, and `BufferedConsumer` using the `credentials` parameter. Service account credentials are used for HTTP Basic Authentication and take precedence over API secrets when both are provided.
- Feature flag providers now support service account credentials for enhanced security. Credentials are automatically passed to `LocalFeatureFlagsProvider` and `RemoteFeatureFlagsProvider` when configured on the `Mixpanel` instance.
- When using `ServiceAccountCredentials`, the `token` parameter is now optional in the `Mixpanel` constructor. The `project_id` from credentials will be used as the token if not explicitly provided.

### Changed
- `ServiceAccountCredentials` now requires `project_id` as a mandatory parameter. This aligns with the service account authentication model where the project ID is essential.
- The `httpx_client_parameters` parameter is now optional in `LocalFeatureFlagsProvider` and `RemoteFeatureFlagsProvider` constructors. When not provided, defaults to basic authentication with the project token. This maintains backward compatibility with existing code that instantiates flag providers directly.
