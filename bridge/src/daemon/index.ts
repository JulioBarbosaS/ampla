/**
 * AMP daemon — persistent process on the dev's machine.
 * Owner of the WS connection to the hub; local inbox; auto-respond; local API for MCP.
 */

import { chmodSync, existsSync, unlinkSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import type { FastifyInstance } from "fastify";
import {
  type DaemonConfig,
  ensureAmpDir,
  loadConfig,
  socketPath,
  storePath,
  usagePath,
} from "../shared/config.js";
import type { AutorespondRecord, ScheduledTaskFrame, WireMessage } from "../shared/protocol.js";
import {
  AutoResponder,
  buildGuardrails,
  type ClaudeRunner,
  defaultClaudeRunner,
  makeDockerRunner,
} from "./auto-responder.js";
import { buildLocalApi } from "./local-api.js";
import { MessageStore } from "./message-store.js";
import { DailyUsageTracker } from "./usage-tracker.js";
import { HubClient } from "./ws-client.js";

/** Automatic replies carry this prefix — and never trigger
 * auto-respond on the other end (anti-loop between two agents in auto mode). */
export const AUTO_REPLY_PREFIX = "[auto] ";

/** How many conversation messages enter the prompt as memory. */
export const HISTORY_LIMIT = 6;

/** Hop-based loop guard: maximum auto-replies within the SAME thread.
 * Third anti-loop layer (besides the [auto] prefix and the type semantics). */
export const MAX_AUTO_REPLIES_PER_THREAD = 5;

/** Transcript reply preview cap (Epic 03 · 3.1). The full reply already lives as
 * a normal message; the audit row only keeps a bounded preview. The opt-in
 * AMP_AUTORESPOND_FULL_TRANSCRIPT widens it for debugging (documented sensitive).
 * The prompt itself is NEVER reported (owner instructions + conversation). */
const FULL_TRANSCRIPT = process.env.AMP_AUTORESPOND_FULL_TRANSCRIPT === "1";
export const REPLY_PREVIEW_MAX = FULL_TRANSCRIPT ? 4000 : 280;

/** Notice sent back to the sender when an auto-respond escalates (the model
 * emitted __ESCALATE__: it couldn't/shouldn't answer). Explains why nothing
 * came back and points to the owner. Sent as an `alert` so the panel shows it in
 * red (Epic 04 · 4.3). */
export function escalationNotice(agentId: string): string {
  return (
    "Não consegui responder a esta mensagem automaticamente. " +
    `Encaminhei ao dono de @${agentId} — para uma resposta, fale diretamente com o responsável pelo agente.`
  );
}

export interface Daemon {
  hub: HubClient;
  store: MessageStore;
  api: FastifyInstance;
  shutdown: () => Promise<void>;
}

export function createDaemon(
  config: DaemonConfig,
  paths: { store: string; usage?: string },
  runner?: ClaudeRunner,
): Daemon {
  const store = new MessageStore(paths.store);
  const hub = new HubClient(config.hub_url, config.agent_id, config.agent_key);
  const usageTracker = new DailyUsageTracker(paths.usage ?? usagePath());
  const responder = new AutoResponder(
    config.agent_id,
    {
      bin: config.claude_bin,
      ...(config.project_dir ? { projectDir: config.project_dir } : {}),
      captureUsage: config.capture_usage,
    },
    runner ?? defaultClaudeRunner,
    Date.now,
    usageTracker,
  );
  const api = buildLocalApi({ agentId: config.agent_id, hub, store });

  // Synchronous reservation of in-flight auto-replies per thread. Without this,
  // concurrent triggers read the store count BEFORE any of them persists the
  // reply and all pass the hop guard (read-then-await-then-write).
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
    // at-least-once: confirm receipt AFTER persisting. Always ack,
    // even if the store deduplicated (repeated id from a resend) — otherwise the hub
    // would resend it forever. The id-based dedup in the store closes the loop.
    if (message.id !== null) hub.ackMessage(message.id);
    void maybeAutoRespond(message);
  });

  async function maybeAutoRespond(message: WireMessage): Promise<void> {
    const settings = hub.settings;
    if (!settings) return;
    // Global kill switch (Epic 03 · 3.2): an admin suspended ALL auto-responders
    // instance-wide. Highest-priority gate — the message still enqueued above.
    if (!hub.autoResponderEnabled) {
      console.error("[amp] kill switch global ativo — auto-resposta suspensa, mensagem na inbox");
      return;
    }
    // Per-agent pause (Epic 03 · 3.2): a fast brake. The owner flipped this agent
    // out of auto-respond without changing `mode`; the message already enqueued
    // in the `message` handler above, so here we just don't drive claude -p.
    if (settings.auto_paused) {
      console.error(`[amp] auto-resposta pausada para ${config.agent_id} — mensagem fica na inbox`);
      return;
    }
    // Anti-loop layer 1/3: an automatic reply does not trigger another reply.
    if (message.body.startsWith(AUTO_REPLY_PREFIX)) return;
    // Layer 2/3 (semantic): only request/task trigger — response/notification/
    // status/ack/alert never trigger.
    if (message.type !== "request" && message.type !== "task") return;

    const conversation = store.conversation(message.from, 50);
    const threadId = message.thread_id;

    // Layer 3/3 (hop guard): cap on auto-replies per thread. The reservation
    // (inFlightByThread) is incremented HERE, synchronously, so concurrent
    // triggers on the same thread see each other's reservations.
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
    // Conversation memory: latest messages enter the prompt as context
    const history = conversation
      .filter((m) => m.id !== message.id)
      .slice(-HISTORY_LIMIT)
      .map((m) => ({ from: m.from, body: m.body, ts: m.ts }));

    // "responding…" indicator: only in auto mode (inbox returns skipped without
    // running the model). A rate-limited run flickers responding→idle briefly,
    // which is harmless.
    const signalsActivity = settings.mode === "auto";
    if (signalsActivity) hub.sendActivity("responding");
    const startedAt = Date.now();
    let result: Awaited<ReturnType<typeof responder.handle>>;
    try {
      result = await responder.handle(message, settings, history);
    } finally {
      if (signalsActivity) hub.sendActivity("idle");
    }
    // Transcript (Epic 03 · 3.1): report every genuine auto-respond attempt
    // (mode=auto). Inbox-mode skips aren't runs; a needs_approval draft is
    // audited as a pending approval (3.3), not as a transcript row.
    if (settings.mode === "auto" && result.kind !== "needs_approval") {
      reportRun(message, settings, result, Date.now() - startedAt);
    }
    const replyOpts = {
      msgType: "response" as const,
      priority: message.priority, // reply inherits the request's priority
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
        // Never send blocked content; the sender gets a neutral notice
        hub.send(
          message.from,
          AUTO_REPLY_PREFIX +
            "Resposta automática bloqueada pelo filtro de segurança. O dono do agente foi notificado.",
          replyOpts,
        );
        console.error(`[amp] resposta bloqueada (${result.reason}) — mensagem de ${message.from}`);
        break;
      case "needs_approval":
        // Don't send: ask the owner. The hub persists the pending approval,
        // notifies the owner, and sends server-side once approved (3.3).
        hub.sendApprovalRequest(message.id, message.from, result.draft);
        console.error(
          `[amp] resposta rascunhada aguardando aprovação do dono — mensagem de ${message.from}`,
        );
        break;
      case "failed":
        console.error(`[amp] auto-respond falhou (${result.reason}) — mensagem segue na inbox`);
        break;
      case "skipped":
        // The model escalated (__ESCALATE__): tell the sender why nothing came
        // back and to reach the owner. Sent as an `alert` (rendered red in the
        // panel); other skips (rate/budget/hours/inbox) just leave it in the inbox.
        if (result.reason === "escalate") {
          hub.send(message.from, AUTO_REPLY_PREFIX + escalationNotice(config.agent_id), {
            msgType: "alert",
            priority: message.priority,
            inReplyTo: message.id,
          });
        }
        break;
    }
  }

  /** Builds and sends the auditable run record (Epic 03 · 3.1). The guardrail
   * snapshot is recomputed from settings (deterministic) so the audit row shows
   * exactly what was in effect for this sender. */
  function reportRun(
    message: WireMessage,
    settings: NonNullable<typeof hub.settings>,
    // needs_approval drafts are audited as approvals (3.3), never as transcript
    // rows — the caller guards this, so the record's result enum stays exact.
    result: Exclude<Awaited<ReturnType<typeof responder.handle>>, { kind: "needs_approval" }>,
    durationMs: number,
  ): void {
    const guardrails = buildGuardrails(settings, message.from);
    const reply = result.kind === "replied" ? result.reply : "";
    const usage = result.kind === "replied" || result.kind === "blocked" ? result.usage : null;
    const record: AutorespondRecord = {
      trigger_message_id: message.id,
      from_sender: message.from,
      result: result.kind,
      reason: result.kind === "replied" ? null : result.reason,
      reply_preview: reply.slice(0, REPLY_PREVIEW_MAX),
      tools_allowed: guardrails.allowedTools,
      tools_disallowed: guardrails.disallowedTools,
      guardrails: {
        allow_write: settings.allow_write,
        block_hidden_files: settings.block_hidden_files,
        block_sensitive_paths: settings.block_sensitive_paths,
        confine_to_dir: settings.confine_to_dir,
        trusted_sender: settings.trusted_senders.includes(message.from),
        sandbox: config.sandbox === "docker" ? "docker" : "host",
      },
      duration_ms: durationMs,
      timed_out: result.kind === "failed" && result.reason === "timeout",
      input_tokens: usage?.input_tokens ?? null,
      output_tokens: usage?.output_tokens ?? null,
      cost_usd: usage?.cost_usd ?? null,
    };
    hub.sendAutorespondReport(record);
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
  hub.on("killSwitch", ({ autoResponderEnabled }) => {
    console.error(
      autoResponderEnabled
        ? "[amp] kill switch global LIBERADO — auto-resposta volta a operar"
        : "[amp] kill switch global ATIVADO pelo admin — auto-resposta suspensa",
    );
  });
  hub.on("broadcastResult", ({ group, sent, skipped, offline }) => {
    console.error(
      `[amp] broadcast ${group}: ${sent.length} enviado(s)` +
        (offline.length ? `, ${offline.length} offline (pendente)` : "") +
        (skipped.length ? `, pulados pela allowlist: ${skipped.join(", ")}` : ""),
    );
  });
  // Scheduled tasks (Epic 08 · 8.4): the hub asks this agent to run an
  // owner-authored (trusted) prompt and reports the outcome back.
  hub.on("scheduledTask", (task: ScheduledTaskFrame) => {
    void runScheduledTask(task);
  });

  async function runScheduledTask(task: ScheduledTaskFrame): Promise<void> {
    const settings = hub.settings;
    if (!settings) {
      hub.sendScheduledTaskReport(task.schedule_id, "failed", "settings indisponíveis");
      return;
    }
    console.error(`[amp] tarefa agendada "${task.name}" (#${task.schedule_id}) → claude -p`);
    const result = await responder.runTask(task.prompt, settings, task.tools === "write");
    hub.sendScheduledTaskReport(task.schedule_id, result.status, result.summary);
  }

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

/** Picks the auto-respond runner from config: the host runner, or the
 * containerized one (claude -p confined to the project dir). */
function selectRunner(config: DaemonConfig): ClaudeRunner {
  if (config.sandbox !== "docker") return defaultClaudeRunner;
  return makeDockerRunner({
    image: config.sandbox_image,
    claudeConfigDir: join(homedir(), ".claude"),
    uid: process.getuid?.() ?? 0,
    gid: process.getgid?.() ?? 0,
  });
}

async function main(): Promise<void> {
  ensureAmpDir();
  const config = loadConfig();
  const daemon = createDaemon(
    config,
    { store: storePath(), usage: usagePath() },
    selectRunner(config),
  );
  if (config.sandbox === "docker") {
    console.error(`[amp] auto-respond em sandbox docker (imagem ${config.sandbox_image})`);
  }

  const sock = socketPath();
  if (existsSync(sock)) unlinkSync(sock); // orphaned socket from a previous run
  await daemon.api.listen({ path: sock });
  chmodSync(sock, 0o600); // only the owner talks to the daemon (Threat 4)

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
