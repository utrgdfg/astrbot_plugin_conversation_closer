# Changelog

All notable changes follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-08-16

### Added

- Three-state LLM judge (`END`, `CONTINUE`, `UNCERTAIN`) with strict JSON validation.
- Fail-open handling for missing providers, timeouts, malformed output, and internal errors.
- Session-isolated bounded histories, message deduplication, per-session locks, and TTL cleanup.
- Silent pre-LLM interception, post-send assistant history capture, and `/closer` commands.
- Privacy documentation, regression dataset, automated tests, linting, and security checks.
