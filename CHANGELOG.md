# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-06-26

### Security

- Bump `undici` to ≥7.28.0 (TLS certificate-validation bypass, WebSocket DoS and
  cross-origin request routing — GHSA) and force the transitive `hono` to ≥4.12.25
  via a pnpm override (CORS reflection). `pnpm audit --prod` is clean again.

### Fixed

- Pin the test timezone to UTC so `MessageBubble` time snapshots are deterministic
  across a developer's machine and the CI runner (they diverged — local TZ vs UTC);
  snapshots regenerated.
- `scripts/ci.sh` now runs the web suite with coverage (`test:cov`), matching the
  GitHub workflow, so the coverage gate and the snapshots are caught pre-push.

## [0.1.0] - 2026-06-26

### Added

- One-image install (hub serves the API, WebSocket and the React panel on one
  URL); multi-arch image published to `ghcr.io` on version tags, so operators
  run it without cloning. TLS via a Caddy overlay.
- `ampla connect <token>` — one command to wire a developer's daemon (config +
  MCP registration + hooks), like registering a GitLab Runner.
- Alembic migrations, applied automatically on container start.
- Admin audit endpoint (`GET /api/users/audit`).
- Readiness probe (`GET /api/health/ready`) that checks the database; the
  container HEALTHCHECK uses it. `GET /api/health` stays liveness.
- Consistent online SQLite backup (`python -m app.db_backup`), including the
  WAL, plus a documented restore flow.
- Supply-chain CI: Dependabot and dependency vulnerability scanning.
- `LICENSE` (MIT), `CONTRIBUTING.md`.

### Security

- Panel session in an HttpOnly, SameSite=Strict cookie (the JWT is no longer
  held in JavaScript / localStorage). The CLI keeps the `Authorization: Bearer`
  header.
- CSP + HSTS, per-route REST rate limiting, bcrypt password hashing with
  incremental login lockout, agent keys stored as sha256, non-root container.
