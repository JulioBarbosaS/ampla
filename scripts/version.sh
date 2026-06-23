#!/usr/bin/env bash
#
# Single source of truth for the product version (Epic 09 · 9.1). The version
# lives in the three ecosystem-native files; this keeps them in lockstep.
#
#   scripts/version.sh            print the version, or fail if the three differ
#   scripts/version.sh --check    same (explicit; used by scripts/ci.sh)
#   scripts/version.sh X.Y.Z      bump all three to X.Y.Z
#
# AMP_REPO_ROOT overrides the repo root (used by scripts/selftest.sh fixtures).

set -euo pipefail

ROOT="${AMP_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYPROJECT="$ROOT/hub/pyproject.toml"
BRIDGE_PKG="$ROOT/bridge/package.json"
WEB_PKG="$ROOT/web/package.json"

_py_version() { grep -m1 '^version = ' "$PYPROJECT" | sed -E 's/.*"([^"]+)".*/\1/'; }
_pkg_version() {
  grep -m1 '"version":' "$1" | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/'
}

_check() {
  local a b c
  a="$(_py_version)"
  b="$(_pkg_version "$BRIDGE_PKG")"
  c="$(_pkg_version "$WEB_PKG")"
  if [[ ! "$a" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "versão do hub não é semver: '$a'" >&2
    return 1
  fi
  if [[ "$a" != "$b" || "$a" != "$c" ]]; then
    echo "versões divergentes — hub=$a bridge=$b web=$c (use scripts/version.sh X.Y.Z)" >&2
    return 1
  fi
  echo "$a"
}

_bump() {
  local v="$1"
  [[ "$v" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]] || {
    echo "versão inválida: '$v' (esperado X.Y.Z)" >&2
    exit 2
  }
  sed -i -E "0,/^version = \".*\"/s//version = \"$v\"/" "$PYPROJECT"
  sed -i -E "0,/\"version\": \".*\"/s//\"version\": \"$v\"/" "$BRIDGE_PKG"
  sed -i -E "0,/\"version\": \".*\"/s//\"version\": \"$v\"/" "$WEB_PKG"
  echo "$v"
}

case "${1:-}" in
  "" | --check) _check ;;
  *) _bump "$1" ;;
esac
