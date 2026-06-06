import { type FormEvent, useEffect, useRef, useState } from "react";
import { messagesApi } from "../../lib/api/messages";
import type { Message } from "../../lib/api/types";
import { conversationKey, useChatStore } from "../../stores/chat";
import { PresenceDot } from "./Sidebar";

export function MessageBubble({ message, mine }: { message: Message; mine: boolean }) {
  const time = new Date(message.created_at).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${
          mine
            ? "rounded-br-sm bg-emerald-700 text-white"
            : "rounded-bl-sm bg-zinc-800 text-zinc-100"
        }`}
      >
        <p className="whitespace-pre-wrap break-words">{message.body}</p>
        <p className={`mt-1 text-right text-[10px] ${mine ? "text-emerald-200/70" : "text-zinc-500"}`}>
          {time}
          {mine && (message.delivered_at ? " · entregue" : " · pendente")}
        </p>
      </div>
    </div>
  );
}

export function ChatWindow() {
  const { perspective, partner, conversations, online } = useChatStore();
  const addMessage = useChatStore((s) => s.addMessage);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const messages =
    perspective && partner ? (conversations[conversationKey(perspective, partner)] ?? []) : [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!perspective || !partner) return;
    const form = event.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const sent = await messagesApi.send(perspective, partner, body);
      addMessage(sent);
      form.reset();
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
          <MessageBubble key={message.id} message={message} mine={message.from === perspective} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="border-t border-zinc-800 p-3">
        {error && (
          <p role="alert" className="mb-2 text-xs text-red-400">
            {error}
          </p>
        )}
        <div className="flex gap-2">
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
