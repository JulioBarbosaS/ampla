#!/usr/bin/env bash
#
# CHANGELOG.md helpers (Epic 09 · 9.3/9.4), Keep a Changelog format.
#
#   scripts/changelog.sh extract X.Y.Z   print the body of the [X.Y.Z] section
#                                         (used to fill a GitHub Release)
#   scripts/changelog.sh cut X.Y.Z DATE  move the [Unreleased] body into a new
#                                         [X.Y.Z] - DATE section (release cut)
#
# AMP_REPO_ROOT overrides the repo root (used by scripts/selftest.sh fixtures).

set -euo pipefail

ROOT="${AMP_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CHANGELOG="$ROOT/CHANGELOG.md"

_extract() {
  local v="$1" out
  out="$(awk -v ver="## [$v]" '
    index($0, ver) == 1 { f = 1; next }
    f && /^## \[/ { exit }
    f { print }
  ' "$CHANGELOG")"
  # strip leading/trailing blank lines
  out="$(printf '%s\n' "$out" | sed -E '/./,$!d' | tac | sed -E '/./,$!d' | tac)"
  if [[ -z "$out" ]]; then
    echo "sem seção [$v] no CHANGELOG" >&2
    return 1
  fi
  printf '%s\n' "$out"
}

_cut() {
  local v="$1" date="$2"
  grep -q '^## \[Unreleased\]' "$CHANGELOG" || {
    echo "CHANGELOG sem seção [Unreleased]" >&2
    exit 1
  }
  awk -v header="## [$v] - $date" '
    /^## \[Unreleased\]/ && !done {
      print
      print ""
      print header
      done = 1
      next
    }
    { print }
  ' "$CHANGELOG" >"$CHANGELOG.tmp"
  mv "$CHANGELOG.tmp" "$CHANGELOG"
}

case "${1:-}" in
  extract) _extract "${2:?uso: changelog.sh extract X.Y.Z}" ;;
  cut) _cut "${2:?uso: changelog.sh cut X.Y.Z DATE}" "${3:?data ausente}" ;;
  *)
    echo "uso: changelog.sh {extract|cut} ..." >&2
    exit 2
    ;;
esac
