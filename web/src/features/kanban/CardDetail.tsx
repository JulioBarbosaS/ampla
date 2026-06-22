import { useEffect, useState } from "react";
import { Markdown } from "../../components/Markdown";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanCard, KanbanComment } from "../../lib/api/types";

/**
 * Card detail (Epic 06 · 6.6): the card body as sanitized Markdown plus the
 * comments thread — the "I need info" channel. Posting a comment notifies the
 * assignee + board owner, and @mentions reach the mentioned agent's owner
 * (hub-side, Epic 06 · 6.5). All via src/lib/api.
 */
export function CardDetail({ card, onClose }: { card: KanbanCard; onClose: () => void }) {
  const [comments, setComments] = useState<KanbanComment[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    kanbanApi
      .listComments(card.id)
      .then(setComments)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar comentários."));
  }, [card.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const comment = await kanbanApi.addComment(card.id, draft.trim());
      setComments((cur) => [...cur, comment]);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao comentar.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Fechar painel"
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      <section
        role="dialog"
        aria-label={`Card: ${card.title}`}
        className="relative z-10 flex h-full w-full max-w-md flex-col gap-3 overflow-y-auto bg-zinc-900 p-4 shadow-xl"
      >
        <header className="flex items-start justify-between gap-2">
          <h2 className="text-base font-semibold text-zinc-100">{card.title}</h2>
          <button
            type="button"
            aria-label="Fechar"
            className="text-zinc-400 hover:text-zinc-200"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className="flex gap-2 text-xs text-zinc-400">
          {card.assignee && <span>Responsável: {card.assignee}</span>}
          <span>Prioridade: {card.priority}</span>
        </div>

        {card.body.trim() && (
          <div className="rounded bg-zinc-800/60 p-2 text-sm text-zinc-100">
            <Markdown>{card.body}</Markdown>
          </div>
        )}

        <h3 className="text-sm font-medium text-zinc-300">Comentários</h3>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <ul className="flex flex-col gap-2">
          {comments.length === 0 && (
            <li className="text-xs text-zinc-500">Nenhum comentário ainda.</li>
          )}
          {comments.map((c) => (
            <li key={c.id} className="rounded bg-zinc-800 p-2 text-sm text-zinc-100">
              <p className="mb-1 text-xs text-zinc-400">{c.author}</p>
              <Markdown>{c.body}</Markdown>
            </li>
          ))}
        </ul>

        <div className="mt-auto flex flex-col gap-2">
          <textarea
            aria-label="Novo comentário"
            className="min-h-[4rem] rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
            placeholder="Comentar… (use @agente para mencionar)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button
            type="button"
            className="self-end rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-40"
            disabled={busy || !draft.trim()}
            onClick={submit}
          >
            Comentar
          </button>
        </div>
      </section>
    </div>
  );
}
