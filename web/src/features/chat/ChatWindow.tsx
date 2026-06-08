import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { messagesApi } from "../../lib/api/messages";
import type { Message, MessageType, Priority } from "../../lib/api/types";
import { conversationKey, useChatStore } from "../../stores/chat";
import { BroadcastPanel } from "./BroadcastPanel";
import { PresenceDot } from "./Sidebar";

/** Prefix for automatic replies (mirrors the daemon's AUTO_REPLY_PREFIX). */
const AUTO_PREFIX = "[auto] ";

const PRIORITY_BADGE: Record<string, string> = {
  urgent: "bg-red-600 text-white",
  high: "bg-amber-600 text-white",
};

const MESSAGE_TYPES: MessageType[] = [
  "request",
  "response",
  "notification",
  "task",
  "alert",
  "status",
  "ack",
];
const PRIORITIES: Priority[] = ["low", "normal", "high", "urgent"];

function stripAuto(body: string): string {
  return body.startsWith(AUTO_PREFIX) ? body.slice(AUTO_PREFIX.length) : body;
}

function preview(text: string, max = 80): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

function ReplyButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="responder"
      title="responder"
      className="shrink-0 self-center rounded-full px-1.5 py-1 text-xs text-zinc-500 opacity-0 transition-opacity hover:bg-zinc-800 hover:text-zinc-200 focus:opacity-100 group-hover:opacity-100"
    >
      ↩
    </button>
  );
}

export function MessageBubble({
  message,
  mine,
  repliedTo,
  answeredBy,
  onReply,
}: {
  message: Message;
  mine: boolean;
  /** Parent message (when this is a reply) — for the compact quote. */
  repliedTo?: Message | null;
  /** Who already answered this question (request/task) — "answered" indicator. */
  answeredBy?: string | null;
  onReply?: (message: Message) => void;
}) {
  const time = new Date(message.created_at).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const badge = PRIORITY_BADGE[message.priority];
  const isAuto = message.body.startsWith(AUTO_PREFIX);
  const text = stripAuto(message.body);
  const isQuestion = message.type === "request" || message.type === "task";
  const replyBtn = onReply ? <ReplyButton onClick={() => onReply(message)} /> : null;

  return (
    <div className={`group flex items-end gap-1 ${mine ? "justify-end" : "justify-start"}`}>
      {mine && replyBtn}
      <div
        className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${
          mine
            ? "rounded-br-sm bg-emerald-700 text-white"
            : "rounded-bl-sm bg-zinc-800 text-zinc-100"
        }`}
      >
        {(badge || isAuto || message.group) && (
          <div className="mb-1 flex flex-wrap items-center gap-1">
            {badge && (
              <span
                className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${badge}`}
              >
                {message.priority}
              </span>
            )}
            {isAuto && (
              <span className="inline-block rounded bg-sky-500/30 px-1.5 py-0.5 text-[10px] font-semibold text-sky-200">
                🤖 auto
              </span>
            )}
            {message.group && (
              <span className="inline-block rounded bg-zinc-700/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-300">
                via {message.group}
              </span>
            )}
          </div>
        )}
        {repliedTo && (
          <div
            className={`mb-1 truncate border-l-2 pl-2 text-xs ${
              mine ? "border-emerald-300/60 text-emerald-100/80" : "border-zinc-600 text-zinc-400"
            }`}
          >
            <span className="font-medium">{repliedTo.from}</span>:{" "}
            {preview(stripAuto(repliedTo.body))}
          </div>
        )}
        <p className="whitespace-pre-wrap break-words">{text}</p>
        <p
          className={`mt-1 flex items-center justify-end gap-1.5 text-[10px] ${
            mine ? "text-emerald-200/70" : "text-zinc-500"
          }`}
        >
          {isQuestion && answeredBy && (
            <span className="text-emerald-300" title={`respondida por ${answeredBy}`}>
              ✓ respondida
            </span>
          )}
          <span>
            {time}
            {mine && (message.delivered_at ? " · entregue" : " · pendente")}
          </span>
        </p>
      </div>
      {!mine && replyBtn}
    </div>
  );
}

export function ChatWindow() {
  const { perspective, partner, conversations, online } = useChatStore();
  const addMessage = useChatStore((s) => s.addMessage);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msgType, setMsgType] = useState<MessageType>("request");
  const [priority, setPriority] = useState<Priority>("normal");
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages = useMemo(
    () =>
      perspective && partner ? (conversations[conversationKey(perspective, partner)] ?? []) : [],
    [perspective, partner, conversations],
  );

  // Lookup by id (quote) and who answered each question ("answered" indicator).
  const { byId, answeredBy } = useMemo(() => {
    const byId = new Map<number, Message>();
    const answeredBy = new Map<number, string>();
    for (const m of messages) byId.set(m.id, m);
    for (const m of messages) {
      if (m.in_reply_to != null && !answeredBy.has(m.in_reply_to)) {
        answeredBy.set(m.in_reply_to, m.from);
      }
    }
    return { byId, answeredBy };
  }, [messages]);

  useEffect(() => {
    if (messages.length > 0) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Switching conversations cancels a pending reply from the previous one.
  // biome-ignore lint/correctness/useExhaustiveDependencies: perspective/partner are switch triggers, not read values
  useEffect(() => {
    setReplyTo(null);
    setMsgType("request");
  }, [perspective, partner]);

  function startReply(message: Message) {
    setReplyTo(message);
    setMsgType("response");
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!perspective || !partner) return;
    const form = event.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await messagesApi.send(perspective, partner, body, {
        type: msgType,
        priority,
        ...(replyTo ? { in_reply_to: replyTo.id } : {}),
      });
      addMessage(sent);
      form.reset();
      setReplyTo(null);
      setMsgType("request");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao enviar.");
    } finally {
      setBusy(false);
    }
  }

  if (!perspective || !partner) {
    return (
      <section className="flex flex-1 items-center justify-center text-zinc-500">
        <p className="max-w-xs text-center text-sm">
          Selecione um agente seu e um membro da equipe para ver a conversa.
        </p>
      </section>
    );
  }

  // Group/@all selected → broadcast mode (no 1:1 timeline).
  if (partner.startsWith("@")) {
    return <BroadcastPanel perspective={perspective} target={partner} />;
  }

  const selectClass =
    "rounded-md border border-zinc-700 bg-zinc-900 px-2 py-2 text-xs text-zinc-300 outline-none focus:border-emerald-500";

  return (
    <section className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-center gap-2.5 border-b border-zinc-800 px-4 py-3">
        <PresenceDot online={online[partner] ?? false} />
        <h2 className="text-sm font-semibold text-zinc-100">{partner}</h2>
        <span className="text-xs text-zinc-500">
          conversando como <span className="text-zinc-300">{perspective}</span>
        </span>
      </header>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="pt-8 text-center text-sm text-zinc-600">
            Nenhuma mensagem ainda. Os agentes (ou você, abaixo) podem começar.
          </p>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            mine={message.from === perspective}
            repliedTo={message.in_reply_to != null ? (byId.get(message.in_reply_to) ?? null) : null}
            answeredBy={answeredBy.get(message.id) ?? null}
            onReply={startReply}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="border-t border-zinc-800 p-3">
        {error && (
          <p role="alert" className="mb-2 text-xs text-red-400">
            {error}
          </p>
        )}
        {replyTo && (
          <div className="mb-2 flex items-center gap-2 rounded-md border-l-2 border-emerald-500 bg-zinc-900 px-2.5 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate text-zinc-400">
              respondendo a <span className="text-zinc-300">{replyTo.from}</span>:{" "}
              {preview(stripAuto(replyTo.body))}
            </span>
            <button
              type="button"
              onClick={() => setReplyTo(null)}
              aria-label="cancelar resposta"
              className="shrink-0 text-zinc-500 hover:text-zinc-200"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <select
            aria-label="tipo da mensagem"
            value={msgType}
            onChange={(e) => setMsgType(e.target.value as MessageType)}
            className={selectClass}
          >
            {MESSAGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            aria-label="prioridade"
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className={selectClass}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            name="body"
            placeholder={`Mensagem para ${partner} (enviada como ${perspective})`}
            autoComplete="off"
            maxLength={16000}
            className="min-w-0 flex-1 rounded-full border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm outline-none transition-colors focus:border-emerald-500"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
          >
            Enviar
          </button>
        </div>
      </form>
    </section>
  );
}
