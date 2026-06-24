import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Markdown } from "../../components/Markdown";
import { ApiError } from "../../lib/api/client";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanCard, KanbanCardOrigin, KanbanComment } from "../../lib/api/types";

const PRIORITIES = ["urgent", "high", "normal", "low"] as const;

/**
 * Card detail (Epic 06 · 6.6): edit the card (title/body/assignee/priority) and
 * delete it, plus the comments thread — the "I need info" channel. Editing uses
 * the optimistic-version PATCH (stale → 409 → reload-and-retry). Posting a
 * comment notifies the assignee + board owner; @mentions reach the mentioned
 * agent's owner (hub-side, Epic 06 · 6.5). All via src/lib/api.
 */
export function CardDetail({
  card,
  boardCards,
  liveComments,
  onClose,
  onChanged,
}: {
  card: KanbanCard;
  boardCards: KanbanCard[];
  /** Comments arriving live for any card (from kanban_delta); CardDetail merges
   * the ones for THIS card, deduped by id, so an open thread stays current. */
  liveComments?: KanbanComment[];
  onClose: () => void;
  onChanged: (card: KanbanCard | null) => void;
}) {
  const [title, setTitle] = useState(card.title);
  const [body, setBody] = useState(card.body);
  const [assignee, setAssignee] = useState(card.assignee ?? "");
  const [priority, setPriority] = useState(card.priority);
  const [comments, setComments] = useState<KanbanComment[]>([]);
  const [deps, setDeps] = useState<KanbanCard[]>([]);
  const [origin, setOrigin] = useState<KanbanCardOrigin | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    kanbanApi
      .listComments(card.id)
      .then(setComments)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar comentários."));
    kanbanApi
      .listDependencies(card.id)
      .then(setDeps)
      .catch(() => {});
    // Resolve the card's origin to a deep-link (Epic 07) — only if it has one.
    if (card.origin) {
      kanbanApi
        .getCardOrigin(card.id)
        .then(setOrigin)
        .catch(() => setOrigin(null));
    } else {
      setOrigin(null);
    }
  }, [card.id, card.origin]);

  function syncDeps(next: KanbanCard[]) {
    setDeps(next);
    // keep the board badge correct without a full reload
    onChanged({ ...card, depends_on: next.map((d) => d.id) });
  }

  async function addDep(depId: number) {
    setError(null);
    try {
      syncDeps(await kanbanApi.addDependency(card.id, depId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao adicionar dependência.");
    }
  }

  async function removeDep(depId: number) {
    try {
      await kanbanApi.removeDependency(card.id, depId);
      syncDeps(deps.filter((d) => d.id !== depId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao remover dependência.");
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await kanbanApi.updateCard(card.id, {
        title: title.trim(),
        body,
        priority,
        ...(assignee.trim() ? { assignee: assignee.trim() } : { clear_assignee: true }),
        expected_version: card.version,
      });
      onChanged(updated);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409)
        setError("O card mudou em outro lugar — feche e reabra para ver a versão atual.");
      else setError(e instanceof Error ? e.message : "Falha ao salvar o card.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy(true);
    try {
      await kanbanApi.deleteCard(card.id);
      onChanged(null);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao excluir o card.");
      setBusy(false);
    }
  }

  async function comment() {
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const c = await kanbanApi.addComment(card.id, draft.trim());
      setComments((cur) => [...cur, c]);
      setDraft("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao comentar.");
    } finally {
      setBusy(false);
    }
  }

  // Loaded comments are the base; live ones for THIS card (e.g. an agent
  // commented while the panel is open) are overlaid at render, deduped by id, so
  // an async (re)load can't clobber them and a duplicate delta is harmless.
  const seenIds = new Set(comments.map((c) => c.id));
  const shownComments = [
    ...comments,
    ...(liveComments ?? []).filter((c) => c.card_id === card.id && !seenIds.has(c.id)),
  ];

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
          <input
            aria-label="Título"
            className="flex-1 rounded bg-zinc-800 px-2 py-1 text-base font-semibold text-zinc-100"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <button
            type="button"
            aria-label="Fechar"
            className="text-zinc-400 hover:text-zinc-200"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        <div className="flex gap-2">
          <input
            aria-label="Responsável"
            className="min-w-0 flex-1 rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
            placeholder="Responsável (slug ou user:<id>)"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
          />
          <select
            aria-label="Prioridade"
            className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
            value={priority}
            onChange={(e) => setPriority(e.target.value as KanbanCard["priority"])}
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        {origin && (
          <p className="text-xs text-zinc-400">
            <span className="text-zinc-500">Origem: </span>
            {origin.available && origin.deep_link ? (
              <button
                type="button"
                className="text-indigo-400 hover:underline"
                onClick={() => origin.deep_link && navigate(origin.deep_link)}
              >
                {origin.label}
              </button>
            ) : (
              <span>{origin.label}</span>
            )}
          </p>
        )}

        <textarea
          aria-label="Descrição"
          className="min-h-[5rem] rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
          placeholder="Descrição (Markdown)…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        {body.trim() && (
          <div className="rounded bg-zinc-800/60 p-2 text-sm text-zinc-100">
            <Markdown>{body}</Markdown>
          </div>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-40"
            disabled={busy || !title.trim()}
            onClick={save}
          >
            Salvar
          </button>
          <button
            type="button"
            className="rounded border border-red-700 px-3 py-1 text-sm text-red-300 hover:bg-red-950/40"
            disabled={busy}
            onClick={remove}
          >
            Excluir card
          </button>
        </div>

        <div className="space-y-1">
          <h3 className="text-sm font-medium text-zinc-300">Bloqueado por</h3>
          <p className="text-xs text-zinc-500">
            Este card só pode ir para uma coluna de conclusão depois que os cards abaixo estiverem
            concluídos.
          </p>
          <ul className="flex flex-col gap-1">
            {deps.length === 0 && <li className="text-xs text-zinc-500">Sem dependências.</li>}
            {deps.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
              >
                <span className="truncate">{d.title}</span>
                <button
                  type="button"
                  aria-label={`Remover dependência ${d.title}`}
                  className="text-xs text-zinc-400 hover:text-red-300"
                  onClick={() => removeDep(d.id)}
                >
                  remover
                </button>
              </li>
            ))}
          </ul>
          <select
            aria-label="Adicionar dependência"
            className="w-full rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
            value=""
            onChange={(e) => e.target.value && addDep(Number(e.target.value))}
          >
            <option value="">+ Depende de…</option>
            {boardCards
              .filter((c) => c.id !== card.id && !deps.some((d) => d.id === c.id))
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
          </select>
        </div>

        <h3 className="text-sm font-medium text-zinc-300">Comentários</h3>
        <ul className="flex flex-col gap-2">
          {shownComments.length === 0 && (
            <li className="text-xs text-zinc-500">Nenhum comentário ainda.</li>
          )}
          {shownComments.map((c) => (
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
            onClick={comment}
          >
            Comentar
          </button>
        </div>
      </section>
    </div>
  );
}
