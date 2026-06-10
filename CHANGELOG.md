# Changelog

Release notes for the `mixpanel` Python package will be added here starting
with the first release made under the standardized release process.

For prior history, see [`CHANGES.txt`](./CHANGES.txt).

## [Unreleased]

### Added
- Service account authentication support via `service_account_username` and `service_account_secret` parameters in `Mixpanel`, `Consumer`, and `BufferedConsumer` classes. Service account credentials are used for HTTP Basic Authentication and take precedence over API secrets when both are provided.
