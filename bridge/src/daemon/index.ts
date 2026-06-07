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

/** Quantas mensagens da conversa entram no prompt como memória. */
export const HISTORY_LIMIT = 6;

/** Loop guard por hops: máximo de auto-respostas numa MESMA thread.
 * Terceira camada anti-loop (além do prefixo [auto] e da semântica de types). */
export const MAX_AUTO_REPLIES_PER_THREAD = 5;

export interface Daemon {
  hub: HubClient;
  store: MessageStore;
  api: FastifyInstance;
  shutdown: () => Promise<void>;
}

export function createDaemon(
  config: DaemonConfig,
  paths: { store: string },
  runner?: ClaudeRunner,
): Daemon {
  const store = new MessageStore(paths.store);
  const hub = new HubClient(config.hub_url, config.agent_id, config.agent_key);
  const responder = new AutoResponder(
    config.agent_id,
    {
      bin: config.claude_bin,
      ...(config.project_dir ? { projectDir: config.project_dir } : {}),
    },
    ...(runner ? [runner] : []),
  );
  const api = buildLocalApi({ agentId: config.agent_id, hub, store });

  // Reserva síncrona de auto-respostas em voo por thread. Sem isso, disparos
  // concorrentes leem a contagem do store ANTES de qualquer um persistir a
  // resposta e todos passam pelo hop guard (read-then-await-then-write).
  const inFlightByThread = new Map<number, number>();

  hub.on("message", (message: WireMessage) => {
    store.append({
      id: message.id,
      from: message.from,
      to: message.to,
      body: message.body,
      type: message.type,
      priority: message.priority,
      group: message.group,
      thread_id: message.thread_id,
      in_reply_to: message.in_reply_to,
      ts: message.created_at,
      direction: "in",
      read: false,
    });
    // at-least-once: confirma o recebimento DEPOIS de persistir. Sempre ackar,
    // mesmo se o store deduplicou (id repetido de um reenvio) — senão o hub a
    // reenviaria para sempre. A dedup por id no store fecha o ciclo.
    if (message.id !== null) hub.ackMessage(message.id);
    void maybeAutoRespond(message);
  });

  async function maybeAutoRespond(message: WireMessage): Promise<void> {
    const settings = hub.settings;
    if (!settings) return;
    // Camada anti-loop 1/3: resposta automática não dispara outra resposta.
    if (message.body.startsWith(AUTO_REPLY_PREFIX)) return;
    // Camada 2/3 (semântica): só request/task disparam — response/notification/
    // status/ack/alert nunca disparam.
    if (message.type !== "request" && message.type !== "task") return;

    const conversation = store.conversation(message.from, 50);
    const threadId = message.thread_id;

    // Camada 3/3 (hop guard): teto de auto-respostas por thread. A reserva
    // (inFlightByThread) é incrementada AQUI, sincronamente, então disparos
    // concorrentes na mesma thread enxergam as reservas uns dos outros.
    if (threadId !== null) {
      const persisted = conversation.filter(
        (m) =>
          m.direction === "out" && m.thread_id === threadId && m.body.startsWith(AUTO_REPLY_PREFIX),
      ).length;
      const reserved = inFlightByThread.get(threadId) ?? 0;
      if (persisted + reserved >= MAX_AUTO_REPLIES_PER_THREAD) {
        console.error(
          `[amp] loop guard: thread ${threadId} atingiu ${MAX_AUTO_REPLIES_PER_THREAD} auto-respostas — mensagem fica na inbox`,
        );
        return;
      }
      inFlightByThread.set(threadId, reserved + 1);
    }

    try {
      await runAutoRespond(message, settings, conversation);
    } finally {
      if (threadId !== null) {
        const left = (inFlightByThread.get(threadId) ?? 1) - 1;
        if (left <= 0) inFlightByThread.delete(threadId);
        else inFlightByThread.set(threadId, left);
      }
    }
  }

  async function runAutoRespond(
    message: WireMessage,
    settings: NonNullable<typeof hub.settings>,
    conversation: ReturnType<typeof store.conversation>,
  ): Promise<void> {
    // Memória de conversa: últimas mensagens entram no prompt como contexto
    const history = conversation
      .filter((m) => m.id !== message.id)
      .slice(-HISTORY_LIMIT)
      .map((m) => ({ from: m.from, body: m.body, ts: m.ts }));

    const result = await responder.handle(message, settings, history);
    const replyOpts = {
      msgType: "response" as const,
      priority: message.priority, // resposta herda a prioridade do pedido
      inReplyTo: message.id,
    };
    switch (result.kind) {
      case "replied": {
        const body = AUTO_REPLY_PREFIX + result.reply;
        if (hub.send(message.from, body, replyOpts)) {
          store.append({
            id: null,
            from: config.agent_id,
            to: message.from,
            body,
            type: "response",
            priority: message.priority,
            group: null,
            thread_id: message.thread_id,
            in_reply_to: message.id,
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
            "Resposta automática bloqueada pelo filtro de segurança. O dono do agente foi notificado.",
          replyOpts,
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
        (ack.pending.length ? ` — ${ack.pending.length} pendente(s)` : ""),
    );
  });
  hub.on("down", ({ willRetry, delayMs }) => {
    console.error(
      willRetry
        ? `[amp] conexão caiu — reconectando em ${Math.round(delayMs / 1000)}s`
        : "[amp] conexão encerrada (sem retry — verifique a chave do agente)",
    );
  });
  hub.on("hubError", ({ code, detail }) => {
    console.error(`[amp] erro do hub: ${code} — ${detail}`);
  });
  hub.on("broadcastResult", ({ group, sent, skipped, offline }) => {
    console.error(
      `[amp] broadcast ${group}: ${sent.length} enviado(s)` +
        (offline.length ? `, ${offline.length} offline (pendente)` : "") +
        (skipped.length ? `, pulados pela allowlist: ${skipped.join(", ")}` : ""),
    );
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
