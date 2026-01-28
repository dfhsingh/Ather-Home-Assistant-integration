# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2026.01.50] - 2026-01-28

### Fixed
- **Split-Stack Architecture**: Fixed critical connection loop by decoupling User Data validation (Router) from Scooter Data fetches (Data Shard).
- **Protocol**: Implemented parsing of `ns` parameter from WebSocket redirects to correctly identify the public Shard URL (`ather-production-mu`).
- **WebSocket**: Stopped reusing Session IDs on redirect to prevent stale "ghost" sessions.
- **Startup**: Increased initial data timeout from 10s to 60s to account for redirect latency.

### Documentation
- Consolidated architecture and API protocol into `private/project_learning.md`.
- Documented the "Split-Brain" database architecture.
