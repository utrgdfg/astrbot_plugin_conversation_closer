# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-20

### Changed

- Simplified the plugin display name and user-facing terminology.
- Grouped WebUI settings into basic controls, judgement, conversation history,
  and advanced sections.
- Added a one-time, versioned migration that preserves existing flat settings
  without allowing stale compatibility values to overwrite later WebUI changes.
- Simplified command output and moved the clickable Mayu counter to the end of
  the README.

### Quality

- Added grouped-setting, legacy-migration, WebUI-layout, and README regression
  coverage.
- Extended the AstrBot source contract check to cover grouped object schemas.

## [0.1.0] - 2026-08-16

### Added

- Three-state LLM judge (`END`, `CONTINUE`, `UNCERTAIN`) with strict JSON validation.
- Fail-open handling for missing providers, timeouts, malformed output, and internal errors.
- Session-isolated bounded histories, message deduplication, per-session locks, and TTL cleanup.
- Silent pre-LLM interception, post-send assistant history capture, and `/closer` commands.
- Privacy documentation, regression dataset, automated tests, linting, and security checks.
