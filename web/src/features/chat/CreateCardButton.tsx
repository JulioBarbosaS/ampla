import { useState } from "react";
import { kanbanApi } from "../../lib/api/kanban";
import type { KanbanBoard } from "../../lib/api/types";

/**
 * "Criar card desta conversa" (Epic 07): turn the open conversation into a
 * kanban card whose `origin` points back at it, so the card deep-links to the
 * thread (and the thread surfaces as the card's origin). The picker loads the
 * user's boards lazily; the card carries a `message` origin keyed by the
 * conversation's latest message — all via src/lib/api (never a raw fetch).
 */
export function CreateCardButton({
  partner,
  lastMessageId,
}: {
  partner: string;
  lastMessageId: number | null;
}) {
  const [open, setOpen] = useState(false);
  const [boards, setBoards] = useState<KanbanBoard[] | null>(null);
  const [boardId, setBoardId] = useState<number | "">("");
  const [title, setTitle] = useState(`Conversa com ${partner}`);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    const next = !open;
    setOpen(next);
    setDone(false);
    setError(null);
    if (next && boards === null) {
      try {
        const list = await kanbanApi.listBoards();
        setBoards(list);
        if (list.length > 0) setBoardId(list[0].id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Falha ao carregar quadros.");
      }
    }
  }

  async function create() {
    if (busy || boardId === "" || !title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await kanbanApi.createCard(boardId, {
        title: title.trim(),
        ...(lastMessageId !== null
          ? { origin: { kind: "message" as const, id: lastMessageId } }
          : {}),
      });
      setDone(true);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao criar o card.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
        onClick={toggle}
      >
        {done ? "Card criado ✓" : "Criar card"}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 flex w-72 flex-col gap-2 rounded border border-zinc-700 bg-zinc-900 p-3 shadow-xl">
          <label className="text-xs text-zinc-400" htmlFor="card-from-convo-title">
            Título
          </label>
          <input
            id="card-from-convo-title"
            aria-label="Título do card"
            className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <label className="text-xs text-zinc-400" htmlFor="card-from-convo-board">
            Quadro
          </label>
          <select
            id="card-from-convo-board"
            aria-label="Quadro de destino"
            className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
            value={boardId}
            onChange={(e) => setBoardId(e.target.value ? Number(e.target.value) : "")}
          >
            {boards?.length === 0 && <option value="">Nenhum quadro</option>}
            {boards?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200"
              onClick={() => setOpen(false)}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-40"
              disabled={busy || boardId === "" || !title.trim()}
              onClick={create}
            >
              Criar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
