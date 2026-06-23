#!/usr/bin/env bash
#
# Single source of truth for the project's quality gates. These are the SAME
# checks the GitHub Actions workflow (.github/workflows/ci.yml) runs — only the
# trigger differs. This script runs them today on plain local git, no remote
# required. When a remote exists later, the workflow keeps calling the same
# commands; nothing here has to change.
#
# Keep this in sync with .github/workflows/ci.yml: a gate added to one belongs
# in the other (the same "change one, change the other" contract as the
# protocol.ts <-> ws.py mirror).
#
# Usage:
#   scripts/ci.sh            core gates: lint + format + types + tests (offline)
#   scripts/ci.sh --audit    + supply-chain audits (pip-audit, pnpm audit; net)
#   scripts/ci.sh --e2e      + real end-to-end (full-stack daemons + Playwright)
#   scripts/ci.sh --all      core + audit + e2e
#   scripts/ci.sh --help     this help
#
# The pre-push hook (.githooks/pre-push) runs the core gates before code leaves
# the machine. Bypass once with `git push --no-verify`.
#
# Exit code is non-zero if ANY gate fails; every gate runs regardless so you see
# all failures in one pass (not just the first).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# ── scope ────────────────────────────────────────────────────────────────────
RUN_CORE=1
RUN_AUDIT=0
RUN_E2E=0
for arg in "$@"; do
  case "$arg" in
    --audit) RUN_AUDIT=1 ;;
    --e2e) RUN_E2E=1 ;;
    --all) RUN_AUDIT=1; RUN_E2E=1 ;;
    -h | --help)
      # print the header comment block (skip the shebang, stop at the first
      # non-comment line), stripping the leading "# ".
      awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "scripts/ci.sh: opção desconhecida '$arg' (use --help)" >&2
      exit 2
      ;;
  esac
done

# ── pretty output + failure tracking ─────────────────────────────────────────
BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[1;31m'; GRN=$'\033[1;32m'
CYN=$'\033[1;36m'; RST=$'\033[0m'
if [ ! -t 1 ]; then BOLD=; DIM=; RED=; GRN=; CYN=; RST=; fi

FAILED=()
section() { printf '\n%s▶ %s%s\n' "$CYN" "$1" "$RST"; }

# run <label> <dir> <cmd...> — execute in <dir>, stream output, record pass/fail.
run() {
  local label="$1" dir="$2"; shift 2
  printf '%s  · %s%s\n' "$DIM" "$label" "$RST"
  if ( cd "$dir" && "$@" ); then
    printf '%s  ✓ %s%s\n' "$GRN" "$label" "$RST"
  else
    printf '%s  ✗ %s%s\n' "$RED" "$label" "$RST"
    FAILED+=("$label")
  fi
}

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "${RED}falta '$1' no PATH${RST} — $2" >&2
    exit 2
  }
}

START=$SECONDS

# ── hub (Python · FastAPI) ───────────────────────────────────────────────────
HUB_BIN="$ROOT/hub/.venv/bin"
if [ ! -x "$HUB_BIN/python" ]; then
  echo "${RED}hub/.venv ausente${RST} — crie com:" >&2
  echo "  cd hub && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 2
fi

if [ "$RUN_CORE" = 1 ]; then
  section "hub · lint + format + testes (cobertura: fail_under=90)"
  run "ruff check" hub "$HUB_BIN/ruff" check app tests
  run "ruff format --check" hub "$HUB_BIN/ruff" format --check app tests
  # pytest roda a suíte inteira, incluindo os golden (openapi.json, ws_frames.json)
  run "pytest --cov" hub "$HUB_BIN/pytest" --cov=app -q
fi

# ── bridge (TypeScript · daemon + MCP) ───────────────────────────────────────
require pnpm "instale o pnpm (corepack enable && corepack prepare pnpm@10 --activate)"

if [ "$RUN_CORE" = 1 ]; then
  section "bridge · lint + tipos + testes (unit + integração)"
  run "biome ci" bridge pnpm exec biome ci .
  run "tsc --noEmit" bridge pnpm exec tsc --noEmit
  # full-stack (tests/e2e) fica no escopo --e2e; aqui unit + integração + golden
  # (o golden trava o mirror ws.py↔protocol.ts; só o full-stack precisa do venv).
  run "vitest (unit+integração+golden)" bridge \
    pnpm exec vitest run tests/unit tests/integration tests/golden
fi

# ── web (React · painel) ─────────────────────────────────────────────────────
if [ "$RUN_CORE" = 1 ]; then
  section "web · lint + tipos + testes"
  run "biome ci" web pnpm exec biome ci .
  run "tsc -b" web pnpm exec tsc -b
  run "vitest" web pnpm exec vitest run
fi

# ── supply-chain audits (opt-in: rede) ───────────────────────────────────────
if [ "$RUN_AUDIT" = 1 ]; then
  section "auditoria de dependências (pip-audit / pnpm audit)"
  run "pip-audit" hub "$HUB_BIN/pip-audit" --skip-editable
  run "pnpm audit (bridge)" bridge pnpm audit --prod --audit-level=high
  run "pnpm audit (web)" web pnpm audit --prod --audit-level=high
fi

# ── end-to-end (opt-in: lento) ───────────────────────────────────────────────
if [ "$RUN_E2E" = 1 ]; then
  section "e2e · hub real ↔ daemons reais + painel (Playwright)"
  run "vitest full-stack" bridge pnpm exec vitest run tests/e2e
  run "playwright e2e" web pnpm e2e
fi

# ── summary ──────────────────────────────────────────────────────────────────
ELAPSED=$((SECONDS - START))
if [ "${#FAILED[@]}" -eq 0 ]; then
  printf '\n%s✓ todos os gates passaram%s (%ds)\n' "$GRN" "$RST" "$ELAPSED"
  exit 0
fi
printf '\n%s✗ %d gate(s) falharam%s (%ds):\n' "$RED" "${#FAILED[@]}" "$RST" "$ELAPSED"
for f in "${FAILED[@]}"; do printf '%s    - %s%s\n' "$RED" "$f" "$RST"; done
exit 1
