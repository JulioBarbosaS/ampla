# Plano — Onboarding do agente + Smoke test real

> Os dois passos que transformam "infraestrutura pronta e testada com mocks" em "Claudes realmente conversando". Executar com contexto fresco. Fazer o **smoke test primeiro** (revela o que falta de verdade), depois o onboarding (corrige a lacuna que o smoke test vai expor).

## Problema

Tudo está verde nos testes, mas: (1) o `claude -p` real, o MCP real e o daemon como serviço **nunca foram ligados de verdade** — o auto-respond só rodou com runner mockado; (2) mesmo ligando, o Claude do outro lado **não sabe que é membro da rede Ampla** — as tools MCP aparecem (descoberta automática), mas nada ensina o Claude a *quando/por que* usá-las nem que ele deve responder mensagens. Falta o "onboarding".

## Parte A — Smoke test real (fazer primeiro, manual + assistido)

Objetivo: provar (ou quebrar) o fluxo `@backend` → auto-respond real → resposta.

Passos:
1. Subir o hub real: `cd hub && .venv/bin/uvicorn app.main:app --port 8000` (AMP_JWT_SECRET setado).
2. Criar admin + 2 agentes (`backend-julio`, `mobile-eduardo`) + chaves via REST/painel.
3. Subir 2 daemons reais com `AMP_HOME` separados, `project_dir` apontando para repos reais, `claude_bin` = caminho do `claude`.
4. Pôr `backend-julio` em modo `auto` (painel/PATCH).
5. Do daemon do mobile, enviar via local-api: `POST /send {to: backend-julio, body: "existe endpoint de reset de senha?"}`.
6. **Observar**: o daemon do backend dispara `claude -p` real → lê o código → responde? A resposta volta à inbox do mobile?

O que provavelmente vai quebrar (verificar/ajustar): flags do `claude -p` (pode ter mudado: `--allowedTools`, `--print`, formato de saída — confirmar com `claude --help`); parsing do stdout (hoje espera texto puro — `claude -p` pode emitir JSON com `--output-format`); o `cwd`/permissões; o tempo (timeout 120s pode ser curto na 1ª chamada). **Registrar cada ajuste como fix com teste.**

Resultado esperado: doc curta "como rodar local" no README + ajustes no `defaultClaudeRunner` se necessário.

## Parte B — Onboarding do agente (hook SessionStart)

Objetivo: o Claude Code "acorda" ciente de que é um agente da rede Ampla.

- Novo hook `bridge/hooks/amp-session-start.sh` (evento `SessionStart` do Claude Code) que consulta o daemon (`GET /status`, `/presence`, `/inbox`) e injeta no contexto via `hookSpecificOutput.additionalContext`:
  ```
  Você é o agente "backend-julio" na rede Ampla da equipe.
  Colegas online agora: mobile-eduardo, infra-maria.
  Você tem N mensagem(ns) não lida(s).
  Use amp_send para perguntar/responder a outros agentes; amp_inbox para ler; amp_presence para ver quem está online.
  Quando tiver dúvida sobre outro serviço, pergunte ao agente responsável em vez de adivinhar.
  ```
- Falha silenciosa (exit 0) se o daemon não estiver rodando — igual ao `amp-inbox.sh`.
- Documentar no README a instalação dos DOIS hooks (`SessionStart` + `UserPromptSubmit`) em `.claude/settings.json`.
- (Opcional) painel mostra um "trecho de CLAUDE.md sugerido" ao criar o agente, como alternativa explícita ao hook.

Sem mudança no hub/protocolo — é só bridge (hook novo) + docs. Teste: o script, dado um daemon fake/fixture, produz o JSON de contexto esperado (pode ser um teste de shell simples ou um vitest que invoca o script).

## Ordem e checklist
- [x] **Runner real validado** (`tests/integration/claude-runner.test.ts`): spawn não-mockado, prompt via `-p`, parsing de stdout, timeout, exit code, cwd — com um `claude` falso (sem gastar a conta).
- [x] B1 hook `amp-session-start.sh` + teste e2e
- [x] B2 README: instalar os 2 hooks
- [ ] **A-interativo (com o Julio):** subir hub + 2 daemons (`pnpm daemon`) + `claude` REAL logado, registrar o MCP (`claude mcp add ampla`), mandar um `@backend` de verdade e ver o auto-respond ler o código e responder. Verificar flags do `claude -p` atual (v2.1.168): confirmar `--allowedTools/--disallowedTools` e se precisa `--output-format`/`--print`. Ajustar `defaultClaudeRunner` se a saída não for texto puro.
- [ ] MCP real no Claude Code + hooks ativos numa sessão real.

**O que sobra é genuinamente interativo** (precisa do `claude` logado, processos vivos, observação ao vivo) — não dá para automatizar em batch. O caminho de processo do runner já está coberto por teste.

## Por que nesta ordem
O smoke test revela se o `claude -p` real funciona (fundação). Não adianta onboarding perfeito se o auto-respond quebra na 1ª chamada real. Depois o onboarding fecha a lacuna de "o Claude não sabe que deve usar a rede" — que o próprio smoke test vai escancarar.
