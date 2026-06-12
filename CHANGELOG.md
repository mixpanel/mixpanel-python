# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class for enhanced security in server-to-server integrations. Service accounts use HTTP Basic Authentication with username/secret/project_id instead of shared API secrets (api_key/api_secret). All three parameters are required and validated (non-empty, non-whitespace).
- `credentials` parameter added to `Mixpanel`, `LocalFeatureFlagsProvider`, and `RemoteFeatureFlagsProvider` constructors to accept `ServiceAccountCredentials`.
- The `credentials` parameter is optional in `LocalFeatureFlagsProvider` and `RemoteFeatureFlagsProvider` constructors, but required if `token` is not provided.