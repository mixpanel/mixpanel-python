# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `ServiceAccountCredentials` class. Pass credentials to `Mixpanel`, `Consumer`, and `BufferedConsumer` using the `credentials` parameter. Service account credentials are used for HTTP Basic Authentication and take precedence over API secrets when both are provided.
