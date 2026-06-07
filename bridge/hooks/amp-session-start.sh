#!/usr/bin/env bash
# Hook SessionStart do Claude Code: faz o Claude "acordar" ciente de que é
# um agente da rede Ampla — quem ele é, quem está online, quantas mensagens
# tem esperando e quais tools usar. Sem isso, as tools MCP aparecem mas o
# Claude não sabe QUANDO/POR QUE usá-las (lacuna de onboarding).
#
# Instalação (settings.json do projeto ou do usuário):
#   "hooks": {
#     "SessionStart": [
#       { "hooks": [{ "type": "command", "command": "/caminho/para/amp-session-start.sh" }] }
#     ]
#   }
#
# Requisitos: daemon AMP rodando, curl e jq. Falha sempre em silêncio
# (exit 0) para nunca atrapalhar a abertura de uma sessão do Claude Code.

set -euo pipefail

SOCK="${AMP_HOME:-$HOME/.amp}/daemon.sock"
[ -S "$SOCK" ] || exit 0
command -v curl >/dev/null && command -v jq >/dev/null || exit 0

STATUS=$(curl -s --max-time 2 --unix-socket "$SOCK" \
  "http://localhost/status" 2>/dev/null) || exit 0

# Extrai identidade, colegas online (menos o próprio) e não-lidas.
CONTEXT=$(printf '%s' "$STATUS" | jq -r '
  (.agent_id // "?") as $me
  | (.online // [] | map(select(. != $me))) as $peers
  | (.unread // 0) as $unread
  | "Você é o agente \"\($me)\" na rede Ampla da equipe — outros agentes Claude colaboram com você por mensagens."
    + "\nColegas online agora: " + (if ($peers | length) > 0 then ($peers | join(", ")) else "ninguém" end) + "."
    + "\nMensagens não lidas esperando você: \($unread)."
    + "\nTools: amp_send (perguntar/responder a um agente ou @grupo/@all), amp_inbox (ler recebidas), amp_history (conversa com alguém), amp_presence (quem está online), amp_groups (grupos), amp_status (seu estado)."
    + "\nQuando tiver dúvida sobre outro serviço da equipe, pergunte ao agente responsável com amp_send em vez de adivinhar; responda mensagens que chegarem para você."
' 2>/dev/null) || exit 0

[ -n "$CONTEXT" ] || exit 0

jq -n --arg ctx "$CONTEXT" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $ctx
  }
}'
