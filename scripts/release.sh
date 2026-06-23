#!/usr/bin/env bash
#
# Cut a release (Epic 09 · 9.3): bump the version, move [Unreleased] into a dated
# section, commit and tag — then STOP. The maintainer pushes deliberately
# (`git push --follow-tags`), which triggers .github/workflows/release.yml to
# build + publish the multi-arch image and the GitHub Release.
#
#   scripts/release.sh X.Y.Z [--skip-ci]
#
# Preconditions (fail closed): clean tree, on main, and scripts/ci.sh green
# (unless --skip-ci). Never pushes. AMP_RELEASE_DATE overrides the date (tests);
# AMP_REPO_ROOT overrides the repo root.

set -euo pipefail

ROOT="${AMP_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="${1:?uso: scripts/release.sh X.Y.Z [--skip-ci]}"
SKIP_CI="${2:-}"
DATE="${AMP_RELEASE_DATE:-$(date +%F)}"

[[ -z "$(git status --porcelain)" ]] || {
  echo "árvore de trabalho suja — faça commit/stash antes de cortar a release" >&2
  exit 1
}
[[ "$(git rev-parse --abbrev-ref HEAD)" == "main" ]] || {
  echo "release só a partir de 'main'" >&2
  exit 1
}
if [[ "$SKIP_CI" != "--skip-ci" ]]; then
  echo "▶ rodando os gates antes da release…"
  "$HERE/ci.sh"
fi

AMP_REPO_ROOT="$ROOT" "$HERE/version.sh" "$VERSION" >/dev/null
AMP_REPO_ROOT="$ROOT" "$HERE/changelog.sh" cut "$VERSION" "$DATE"

git add hub/pyproject.toml bridge/package.json web/package.json CHANGELOG.md
git commit -q -m "chore(release): v$VERSION"
git tag -a "v$VERSION" -m "v$VERSION"

echo "✓ v$VERSION cortada e tagueada (sem push)."
echo "  Para publicar a imagem + release: git push --follow-tags"
