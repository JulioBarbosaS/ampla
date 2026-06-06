#!/usr/bin/env bash
# Hook UserPromptSubmit do Claude Code: injeta mensagens AMP não lidas
# no contexto a cada prompt do dev — o Claude fica sabendo das perguntas
# de outros agentes sem o dev pedir.
#
# Instalação (settings.json do projeto ou do usuário):
#   "hooks": {
#     "UserPromptSubmit": [
#       { "hooks": [{ "type": "command", "command": "/caminho/para/amp-inbox.sh" }] }
#     ]
#   }
#
# Requisitos: daemon AMP rodando, curl e jq. Falha sempre em silêncio
# (exit 0) para nunca atrapalhar o uso normal do Claude Code.

set -euo pipefail

SOCK="${AMP_HOME:-$HOME/.amp}/daemon.sock"
[ -S "$SOCK" ] || exit 0
command -v curl >/dev/null && command -v jq >/dev/null || exit 0

RESPONSE=$(curl -s --max-time 2 --unix-socket "$SOCK" \
  "http://localhost/inbox?unread_only=true&mark_read=true" 2>/dev/null) || exit 0

COUNT=$(printf '%s' "$RESPONSE" | jq -r '.messages | length' 2>/dev/null) || exit 0
[ "${COUNT:-0}" -gt 0 ] 2>/dev/null || exit 0

CONTEXT=$(printf '%s' "$RESPONSE" | jq -r \
  '.messages[] | "- de \(.from) em \(.ts): \(.body)"')

jq -n --arg ctx "$CONTEXT" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: ("📨 Mensagens AMP de outros agentes (responda com a tool amp_send se fizer sentido):\n" + $ctx)
  }
}'
