#!/usr/bin/env bash
#
# Self-tests for the release tooling + git hooks (Epic 09). Pure shell, no deps;
# run by scripts/ci.sh. Everything operates on a throwaway repo (AMP_REPO_ROOT),
# never the real tree.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PASS=0
FAIL=0
assert() { if eval "$2"; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); echo "  ✗ $1"; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/hub" "$TMP/bridge" "$TMP/web"
printf '[project]\nname = "x"\nversion = "0.1.0"\n' >"$TMP/hub/pyproject.toml"
printf '{\n  "name": "b",\n  "version": "0.1.0"\n}\n' >"$TMP/bridge/package.json"
printf '{\n  "name": "w",\n  "version": "0.1.0"\n}\n' >"$TMP/web/package.json"
cat >"$TMP/CHANGELOG.md" <<'MD'
# Changelog

## [Unreleased]

### Added

- thing one
MD

export AMP_REPO_ROOT="$TMP"

# ---- version.sh ----
assert "version --check equal" '[[ "$("$HERE/version.sh" --check)" == "0.1.0" ]]'
"$HERE/version.sh" 1.2.3 >/dev/null
assert "bump hub" 'grep -q "version = \"1.2.3\"" "$TMP/hub/pyproject.toml"'
assert "bump bridge" 'grep -q "\"version\": \"1.2.3\"" "$TMP/bridge/package.json"'
assert "bump web" 'grep -q "\"version\": \"1.2.3\"" "$TMP/web/package.json"'
assert "check after bump" '[[ "$("$HERE/version.sh" --check)" == "1.2.3" ]]'
sed -i 's/"version": "1.2.3"/"version": "9.9.9"/' "$TMP/web/package.json"
assert "check detects divergence" '! "$HERE/version.sh" --check 2>/dev/null'
sed -i 's/"version": "9.9.9"/"version": "1.2.3"/' "$TMP/web/package.json"

# ---- changelog.sh ----
"$HERE/changelog.sh" cut 1.2.3 2026-07-01
assert "cut adds dated section" 'grep -q "## \[1.2.3\] - 2026-07-01" "$TMP/CHANGELOG.md"'
assert "cut keeps Unreleased" 'grep -q "## \[Unreleased\]" "$TMP/CHANGELOG.md"'
assert "extract returns moved body" '[[ "$("$HERE/changelog.sh" extract 1.2.3)" == *"thing one"* ]]'
assert "extract missing fails" '! "$HERE/changelog.sh" extract 5.0.0 2>/dev/null'

# ---- commit-msg hook ----
_msg() { printf '%s\n' "$1" >"$TMP/msg"; "$ROOT/.githooks/commit-msg" "$TMP/msg" 2>/dev/null; }
assert "good msg passes" '_msg "feat(hub): add X"'
assert "multi-scope passes" '_msg "fix(hub,web): bug"'
assert "breaking marker passes" '_msg "feat(hub)!: drop Y"'
assert "non-conventional rejected" '! _msg "update stuff"'
assert "wrong-case type rejected" '! _msg "Feat: x"'
assert "merge commit allowed" '_msg "Merge branch main"'

# ---- release.sh (end to end in a temp git repo) ----
(
  cd "$TMP" && git init -q && git config user.email t@t && git config user.name t &&
    git add -A && git commit -q -m "chore: seed" && git branch -M main
)
AMP_RELEASE_DATE=2026-07-02 "$HERE/release.sh" 2.0.0 --skip-ci >/dev/null 2>&1
assert "release tags vX.Y.Z" '(cd "$TMP" && git rev-parse -q --verify refs/tags/v2.0.0 >/dev/null)'
assert "release bumped version" 'grep -q "version = \"2.0.0\"" "$TMP/hub/pyproject.toml"'
assert "release commit subject" '(cd "$TMP" && git log -1 --pretty=%s | grep -q "chore(release): v2.0.0")'
echo dirty >"$TMP/dirty.txt"
assert "release refuses dirty tree" '! AMP_RELEASE_DATE=2026-07-03 "$HERE/release.sh" 3.0.0 --skip-ci 2>/dev/null'

echo ""
echo "tooling selftest: ${PASS} passou, ${FAIL} falhou"
[[ "$FAIL" -eq 0 ]]
