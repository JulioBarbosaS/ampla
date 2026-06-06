/**
 * Daemon AMP — processo persistente na máquina do dev.
 * Dono da conexão WS com o hub; inbox local; auto-respond; API local p/ MCP.
 */

import { chmodSync, existsSync, unlinkSync } from "node:fs";
import { pathToFileURL } from "node:url";
import type { FastifyInstance } from "fastify";
import {
  type DaemonConfig,
  ensureAmpDir,
  loadConfig,
  socketPath,
  storePath,
} from "../shared/config.js";
import type { WireMessage } from "../shared/protocol.js";
import { AutoResponder, type ClaudeRunner } from "./auto-responder.js";
import { buildLocalApi } from "./local-api.js";
import { MessageStore } from "./message-store.js";
import { HubClient } from "./ws-client.js";

/** Respostas automáticas carregam este prefixo — e nunca disparam
 * auto-respond na outra ponta (anti-loop entre dois agentes em modo auto). */
export const AUTO_REPLY_PREFIX = "[auto] ";

export interface Daemon {
  hub: HubClient;
  store: MessageStore;
  api: FastifyInstance;
  shutdown: () => Promise<void>;
}

export function createDaemon(
  config: DaemonConfig,
  paths: { store: string },
  runner?: ClaudeRunner
): Daemon {
  const store = new MessageStore(paths.store);
  const hub = new HubClient(config.hub_url, config.agent_id, config.agent_key);
  const responder = new AutoResponder(
    config.agent_id,
    {
      bin: config.claude_bin,
      ...(config.project_dir ? { projectDir: config.project_dir } : {}),
    },
    ...(runner ? [runner] : [])
  );
  const api = buildLocalApi({ agentId: config.agent_id, hub, store });

  hub.on("message", (message: WireMessage) => {
    store.append({
      id: message.id,
      from: message.from,
      to: message.to,
      body: message.body,
      ts: message.created_at,
      direction: "in",
      read: false,
    });
    void maybeAutoRespond(message);
  });

  async function maybeAutoRespond(message: WireMessage): Promise<void> {
    const settings = hub.settings;
    if (!settings) return;
    if (message.body.startsWith(AUTO_REPLY_PREFIX)) return; // anti-loop

    const result = await responder.handle(message, settings);
    switch (result.kind) {
      case "replied": {
        const body = AUTO_REPLY_PREFIX + result.reply;
        if (hub.send(message.from, body)) {
          store.append({
            id: null,
            from: config.agent_id,
            to: message.from,
            body,
            ts: new Date().toISOString(),
            direction: "out",
            read: true,
          });
        }
        break;
      }
      case "blocked":
        // Nunca enviar conteúdo bloqueado; o remetente recebe aviso neutro
        hub.send(
          message.from,
          AUTO_REPLY_PREFIX +
            "Resposta automática bloqueada pelo filtro de segurança. O dono do agente foi notificado."
        );
        console.error(`[amp] resposta bloqueada (${result.reason}) — mensagem de ${message.from}`);
        break;
      case "failed":
        console.error(`[amp] auto-respond falhou (${result.reason}) — mensagem segue na inbox`);
        break;
      case "skipped":
        break; // inbox mode ou rate limit: mensagem fica na inbox para o dono
    }
  }

  hub.on("ack", (ack) => {
    console.error(
      `[amp] conectado como ${ack.agent_id} — online: ${ack.online.join(", ") || "ninguém"}` +
        (ack.pending.length ? ` — ${ack.pending.length} pendente(s)` : "")
    );
  });
  hub.on("down", ({ willRetry, delayMs }) => {
    console.error(
      willRetry
        ? `[amp] conexão caiu — reconectando em ${Math.round(delayMs / 1000)}s`
        : "[amp] conexão encerrada (sem retry — verifique a chave do agente)"
    );
  });
  hub.on("hubError", ({ code, detail }) => {
    console.error(`[amp] erro do hub: ${code} — ${detail}`);
  });

  return {
    hub,
    store,
    api,
    shutdown: async () => {
      hub.stop();
      await api.close();
    },
  };
}

async function main(): Promise<void> {
  ensureAmpDir();
  const config = loadConfig();
  const daemon = createDaemon(config, { store: storePath() });

  const sock = socketPath();
  if (existsSync(sock)) unlinkSync(sock); // socket órfão de execução anterior
  await daemon.api.listen({ path: sock });
  chmodSync(sock, 0o600); // só o dono fala com o daemon (Ameaça 4)

  daemon.hub.start();
  console.error(`[amp] daemon ativo — agente ${config.agent_id}, socket ${sock}`);

  const stop = async () => {
    await daemon.shutdown();
    if (existsSync(sock)) unlinkSync(sock);
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    console.error(`[amp] erro fatal: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  });
}
