# Epic 09 — Release Engineering & Dev Hooks

> From the project-suggestions list · **item #8** (versioned releases + CHANGELOG
> + pre-commit hooks).

The plumbing that turns "green on `main`" into a **versioned, reproducible
release** — and that keeps the contributor's local loop honest before code ever
reaches CI. Most of the destination already exists: `release.yml` builds and
pushes a multi-arch image to `ghcr.io` on a `v*` tag, `CHANGELOG.md` follows Keep
a Changelog, commits are 100% Conventional Commits, and `scripts/ci.sh` +
`.githooks/pre-push` (Epic-less, just shipped) run every gate locally. What's
missing is the **release ritual** that ties them together and the **commit-time**
hooks that catch problems a second earlier.

This epic is **tooling, not product** — no DB, no migration, no WS frames. Its
"tests in the same commit" are script tests + a version-sync gate wired into the
existing `scripts/ci.sh`/CI.

Files in play: `scripts/{release.sh,version.sh,ci.sh}`, `.githooks/{pre-commit,commit-msg}`,
`hub/pyproject.toml`, `bridge/package.json`, `web/package.json`, `CHANGELOG.md`,
`.github/workflows/release.yml`, `CONTRIBUTING.md`, `docs/`.

> Builds on: the local CI runner (`scripts/ci.sh`, `core`/`--audit`/`--e2e`/`--all`
> scopes) and the `core.hooksPath=.githooks` wiring; the existing `release.yml`
> (tag `v*` → `ghcr.io/<owner>/ampla` via `docker/metadata-action` semver); the
> Conventional Commits discipline in CONTRIBUTING.

## Current state (grounding)

- **Versions: three hand-maintained copies, all `0.1.0`** —
  `hub/pyproject.toml` (`version`), `bridge/package.json`, `web/package.json`. No
  single source; they happen to match today but nothing enforces it.
- **CHANGELOG.md:** Keep a Changelog + SemVer, everything under `## [Unreleased]`
  (`### Added`/`### Security`), hand-curated. **No released section yet** (no
  `## [0.1.0]`).
- **No git tags** (`git tag` is empty). `release.yml` fires on `push: tags: v*`
  and derives the image semver **from the tag** via `metadata-action`; the
  `Dockerfile` is versionless. So **the tag is the release trigger and the version
  source** — but nothing creates the tag or syncs the package versions to it.
- **Hooks:** only `.githooks/pre-push` (runs `scripts/ci.sh`). No
  `.pre-commit-config.yaml`, husky, lefthook, or commitlint config (the husky under
  `bridge/node_modules/**` is a transitive dep, not ours).
- **Lint/format already standardized:** `ruff check`/`ruff format` (hub),
  `biome ci`/`biome check --write` (bridge/web) — the hooks reuse these verbatim.

---

## 9.1 Version single-source + sync gate · `◻ planned` · risk: low

**Goal.** One command bumps all three package versions together, and a gate fails
the build if they ever drift.

**Design — keep ecosystem-native files, enforce equality.** Don't introduce a
foreign `VERSION` file the three toolchains would ignore; instead keep
`pyproject.toml` / `package.json` ×2 as the idiomatic homes and add:

- `scripts/version.sh` — prints the three versions; `scripts/version.sh <x.y.z>`
  rewrites all three (and is the only sanctioned way to bump). Pure text edits, no
  new deps.
- A **sync check** wired into `scripts/ci.sh` core and a tiny hub golden/unit
  (`tests/golden` or `tests/unit/test_version_sync.py`) asserting the three values
  are equal and SemVer-shaped. The check is the "test in the same commit."

**Tests.** The version-sync test fails when the three differ and passes when they
match; `version.sh <x.y.z>` updates all three to the same value (asserted by
re-reading them).

**Effort.** ~0.5 day.

---

## 9.2 Commit-time hooks: format + Conventional Commits · `◻ planned` · risk: low

**Goal.** Catch a mis-formatted file or a non-conventional commit message at
commit time — a second before pre-push runs the full suite.

**Design — extend `.githooks` (already wired via `core.hooksPath`), no heavy deps.**

- `.githooks/pre-commit` — **fast** and **staged-only**: `ruff format --check` +
  `biome check` over the staged files in each package (skip a package with no
  staged changes). Fast enough to run on every commit; the *full* lint/type/test
  suite stays at `pre-push` (`scripts/ci.sh`). Bypass with `git commit --no-verify`.
- `.githooks/commit-msg` — validate the message against the Conventional Commits
  shape the project already follows (`type(scope): subject`, allowed types
  `feat|fix|docs|test|ci|chore|refactor|perf|build`, scopes `hub|bridge|web|specs|…`),
  via a small POSIX-shell/regex validator (≈30 lines) — **decision: no commitlint/
  Node dependency**, consistent with the "no foreign tooling" choice in 9.1 and the
  fact that the hook must run for hub-only contributors who may not have `pnpm`.
- Document enabling (`git config core.hooksPath .githooks`, already in CONTRIBUTING)
  and that the validator's allow-list lives next to the hook.

**Tests.** The commit-msg validator is a unit-testable pure function/script: a
table of good messages (the real recent commits) pass, bad ones
(`update stuff`, `Feat: x`, `feat x`) fail. The pre-commit hook is exercised by a
shell test that stages a badly-formatted file and asserts a non-zero exit.

**Effort.** ~1 day.

---

## 9.3 The release ritual: cut, changelog, tag · `◻ planned` · risk: med

**Goal.** One reviewed command takes `[Unreleased]` to a tagged release that
triggers the existing image build.

**Design.** `scripts/release.sh <x.y.z>`:
1. **Preconditions** (fail closed): clean working tree, on `main`, up to date, and
   `scripts/ci.sh` green (or `--all`). No release off a dirty/feature branch.
2. **Bump** via `scripts/version.sh <x.y.z>` (9.1).
3. **CHANGELOG:** move `## [Unreleased]` content into `## [x.y.z] - <date>`, leave a
   fresh empty `[Unreleased]`. The date is passed in / read from `git` (no
   nondeterministic wall-clock baked into a test). Optionally **seed** the section
   from Conventional Commits since the last tag (`git log <lasttag>..HEAD`) grouped
   by type — a helper that drafts; the human still curates (the CHANGELOG stays
   hand-reviewed, matching today's practice).
4. **Commit** `chore(release): vX.Y.Z` and **annotated tag** `vX.Y.Z`.
5. Print the next step: `git push --follow-tags` → `release.yml` builds
   `ghcr.io/<owner>/ampla:X.Y.Z` (+ `X.Y`, sha). The script **does not push** — the
   maintainer pushes deliberately (consistent with "commit/push only when asked").

This adds nothing to `release.yml`; it *feeds* it. Until a remote exists, the tag
sits locally and the day a remote is added, `git push --follow-tags` ships it —
the same local-first → CI-ready story as `scripts/ci.sh`.

**Tests.** A shell test runs `release.sh` against a throwaway temp git repo
fixture (injected date): asserts the three versions bumped, the CHANGELOG section
moved with a fresh `[Unreleased]`, the `chore(release)` commit + `vX.Y.Z` tag
exist, and that a dirty tree / non-`main` / red CI **aborts** before any mutation.

**Effort.** ~1.5 days.

---

## 9.4 GitHub Release notes (remote-ready) · `◻ planned` · risk: low

**Goal.** When a remote exists, the tag also publishes a GitHub Release whose body
is the CHANGELOG section for that version — no manual copy-paste.

**Design.** Add a job/step to `release.yml` (alongside the image build) that, on a
`v*` tag, extracts the matching `## [x.y.z]` block from `CHANGELOG.md` and creates
the GitHub Release with it (`softprops/action-gh-release` or `gh release create`).
Pure addition, gated by the same `v*` trigger; inert without a remote (like the
rest of the workflows today). Document the end-to-end flow (cut → tag → push →
image + release) in `CONTRIBUTING.md`/`docs`.

**Tests.** The CHANGELOG-extraction step is a small script unit-tested against a
fixture CHANGELOG (returns exactly the requested version's block, errors if the
version is absent). The workflow change is validated by `actionlint` in CI if
present, else by review.

**Effort.** ~0.5 day.

---

## Deferred to a follow-up (noted, not built)

- **Fully automated changelog** (release-please / semantic-release) — heavier and
  opinionated; the spec keeps the CHANGELOG human-curated with a commit-derived
  *draft*, not full automation.
- **Signed tags / provenance (SLSA, cosign)** — supply-chain hardening worth doing
  once public, but a separate security epic (pairs with suggestion #2).
- **Per-package independent versioning** — v1 keeps the three lockstep (one product,
  one version); split only if the daemon/panel ever ship separately.

---

## Epic 09 milestone checklist

- [ ] 9.1 `scripts/version.sh` + version-sync gate in `scripts/ci.sh`/CI + test
- [ ] 9.2 `.githooks/pre-commit` (staged format/lint) + `.githooks/commit-msg`
  (Conventional Commits validator) + validator test; CONTRIBUTING updated
- [ ] 9.3 `scripts/release.sh` (preconditions → bump → CHANGELOG cut → commit +
  tag; never pushes) + temp-repo test
- [ ] 9.4 `release.yml` publishes GitHub Release from the CHANGELOG section
  (remote-ready, inert without one) + extraction test
- [ ] No new runtime deps; hooks run for hub-only contributors (no `pnpm` required)
- [ ] Tooling tests run inside `scripts/ci.sh` core like every other gate

Recommended order: 9.1 (unblocks the rest) → 9.2 (independent, immediate value) →
9.3 (the ritual) → 9.4 (remote-only polish).

---

## Sources

- Keep a Changelog: https://keepachangelog.com/en/1.1.0/ · Semantic Versioning:
  https://semver.org/
- Conventional Commits: https://www.conventionalcommits.org/
- Existing release pipeline: [`../../.github/workflows/release.yml`](../../.github/workflows/release.yml)
  (tag `v*` → multi-arch `ghcr.io` image via `docker/metadata-action`)
- Local CI runner this builds on: `scripts/ci.sh`, `.githooks/pre-push`,
  [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)
