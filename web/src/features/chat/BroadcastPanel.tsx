import { type FormEvent, useState } from "react";
import { type BroadcastResult, messagesApi } from "../../lib/api/messages";
import type { MessageType, Priority } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";
import { PresenceDot } from "./Sidebar";

const BROADCAST_TYPES: MessageType[] = ["notification", "request", "task", "alert", "status"];
const PRIORITIES: Priority[] = ["low", "normal", "high", "urgent"];

/** Broadcast panel: shown when the selected "partner" is a group (@slug)
 * or @all. Sends a broadcast and shows the fan-out result. */
export function BroadcastPanel({ perspective, target }: { perspective: string; target: string }) {
  const { directory, groups, online } = useChatStore();
  const [msgType, setMsgType] = useState<MessageType>("notification");
  const [priority, setPriority] = useState<Priority>("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BroadcastResult | null>(null);

  const members =
    target === "@all"
      ? directory.map((d) => d.slug)
      : (groups.find((g) => `@${g.slug}` === target)?.members ?? []);

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = String(new FormData(form).get("body") ?? "").trim();
    if (!body) return;
    setBusy(true);
    setError(null);
    try {
      const res = await messagesApi.broadcast(perspective, target, body, {
        type: msgType,
        priority,
      });
      setResult(res);
      form.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao transmitir.");
    } finally {
      setBusy(false);
    }
  }

  const selectClass =
    "rounded-md border border-zinc-700 bg-zinc-900 px-2 py-2 text-xs text-zinc-300 outline-none focus:border-emerald-500";

  return (
    <section className="flex min-w-0 flex-1 flex-col">
      <header className="border-b border-zinc-800 px-4 py-3">
        <h2 className="font-mono text-sm font-semibold text-emerald-300">{target}</h2>
        <p className="text-xs text-zinc-500">
          modo transmissão · enviando como <span className="text-zinc-300">{perspective}</span>
        </p>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
          Destinatários ({members.length})
        </p>
        {members.length === 0 ? (
          <p className="text-sm text-zinc-500">
            Este grupo ainda não tem membros — adicione agentes em “Grupos”.
          </p>
        ) : (
          <ul className="space-y-1">
            {members.map((slug) => (
              <li key={slug} className="flex items-center gap-2 text-sm text-zinc-300">
                <PresenceDot online={online[slug] ?? false} />
                <span className="font-mono">{slug}</span>
              </li>
            ))}
          </ul>
        )}

        {result && (
          <div className="mt-4 rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm">
            <p className="text-emerald-300">
              ✓ {result.sent.length} enviado(s)
              {result.skipped.length > 0 && (
                <span className="text-amber-300">
                  {" "}
                  · {result.skipped.length} não recebe(m): {result.skipped.join(", ")} (bloquearam
                  seu agente na allowlist)
                </span>
              )}
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              Quem está offline recebe ao reconectar (mensagens ficam pendentes).
            </p>
          </div>
        )}
      </div>

      <form onSubmit={handleSend} className="border-t border-zinc-800 p-3">
        {error && (
          <p role="alert" className="mb-2 text-xs text-red-400">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <select
            aria-label="tipo da mensagem"
            value={msgType}
            onChange={(e) => setMsgType(e.target.value as MessageType)}
            className={selectClass}
          >
            {BROADCAST_TYPES.map((t) => (
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
            placeholder={`Transmitir para ${target} (${members.length} agente(s))`}
            autoComplete="off"
            maxLength={16000}
            className="min-w-0 flex-1 rounded-full border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm outline-none transition-colors focus:border-emerald-500"
          />
          <button
            type="submit"
            disabled={busy}
            className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
          >
            Transmitir
          </button>
        </div>
      </form>
    </section>
  );
}
