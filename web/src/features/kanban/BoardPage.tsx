import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../lib/api/client";
import { cardsOf, kanbanApi, sortColumns } from "../../lib/api/kanban";
import type { KanbanBoard, KanbanBoardFull, KanbanCard } from "../../lib/api/types";
import { connectObserver } from "../../lib/ws/observer";
import { useAuthStore } from "../../stores/auth";
import { BoardSettings } from "./BoardSettings";
import { CardDetail } from "./CardDetail";

/**
 * Kanban board view (Epic 06 · 6.6). Reads via src/lib/api, lives via the
 * observer's kanban_delta (never fetches directly). v1 uses explicit move
 * actions (← →) on the anchor-based API — drag-and-drop is a later refinement on
 * the same endpoint. A move is optimistic and rolls back (refetch) on a 409.
 *
 * This is the minimal functional slice; the richer grants/danger-zone panel and
 * card detail come in the dedicated UI pass.
 */
export function BoardPage() {
  const [boards, setBoards] = useState<KanbanBoard[] | null>(null);
  const [boardId, setBoardId] = useState<number | null>(null);
  const [full, setFull] = useState<KanbanBoardFull | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [openCardId, setOpenCardId] = useState<number | null>(null);
  const user = useAuthStore((s) => s.user);
  const canManage = !!full && !!user && (user.id === full.board.owner_id || user.role === "admin");

  useEffect(() => {
    kanbanApi
      .listBoards()
      .then((list) => {
        setBoards(list);
        if (list.length > 0) setBoardId((id) => id ?? list[0].id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar quadros."));
  }, []);

  const reload = useCallback((id: number) => {
    kanbanApi
      .getBoardFull(id)
      .then(setFull)
      .catch((e) => setError(e instanceof Error ? e.message : "Falha ao carregar o quadro."));
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: reload is stable
  useEffect(() => {
    if (boardId !== null) reload(boardId);
  }, [boardId]);

  // Live deltas: apply only for the board on screen; reconcile by upsert/remove.
  useEffect(() => {
    if (boardId === null) return;
    return connectObserver({
      onMessage: () => {},
      onPresence: () => {},
      onOnlineList: () => {},
      onKanbanDelta: (delta) => {
        if (delta.board_id !== boardId) return;
        if (delta.op === "comment_added") return; // comments aren't shown in v1
        setFull((cur) => {
          if (!cur) return cur;
          if (delta.op === "card_deleted" && delta.card) {
            return { ...cur, cards: cur.cards.filter((c) => c.id !== delta.card?.id) };
          }
          if (!delta.card) return cur;
          const others = cur.cards.filter((c) => c.id !== delta.card?.id);
          return { ...cur, cards: [...others, delta.card] };
        });
      },
    });
  }, [boardId]);

  async function createCard() {
    if (boardId === null || !newTitle.trim()) return;
    setNewTitle("");
    try {
      const card = await kanbanApi.createCard(boardId, { title: newTitle.trim() });
      setFull((cur) => (cur ? { ...cur, cards: [...cur.cards, card] } : cur));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao criar o card.");
    }
  }

  async function moveTo(card: KanbanCard, toColumnId: number) {
    if (boardId === null) return;
    const previous = full;
    // optimistic: drop the card at the end of the destination column
    setFull((cur) =>
      cur
        ? {
            ...cur,
            cards: cur.cards.map((c) => (c.id === card.id ? { ...c, column_id: toColumnId } : c)),
          }
        : cur,
    );
    try {
      const moved = await kanbanApi.moveCard(card.id, {
        to_column_id: toColumnId,
        expected_version: card.version,
      });
      setFull((cur) =>
        cur ? { ...cur, cards: cur.cards.map((c) => (c.id === moved.id ? moved : c)) } : cur,
      );
    } catch (e) {
      // 409 (stale version) or any failure → roll back and refetch the truth
      if (previous) setFull(previous);
      if (e instanceof ApiError && e.status === 409) reload(boardId);
      else setError(e instanceof Error ? e.message : "Falha ao mover o card.");
    }
  }

  if (boards !== null && boards.length === 0) {
    return (
      <CreateFirstBoard
        onCreated={(b) => {
          setBoards([b]);
          setBoardId(b.id);
        }}
      />
    );
  }

  const columns = full ? sortColumns(full.columns) : [];
  const openCard = full?.cards.find((c) => c.id === openCardId) ?? null;

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-zinc-100">Quadro</h1>
        {boards && boards.length > 1 && (
          <select
            aria-label="Quadro"
            className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-200"
            value={boardId ?? ""}
            onChange={(e) => setBoardId(Number(e.target.value))}
          >
            {boards.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        )}
        {canManage && (
          <button
            type="button"
            className="ml-auto rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
            onClick={() => setShowSettings((s) => !s)}
          >
            Permissões
          </button>
        )}
      </header>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {showSettings && canManage && full && (
        <BoardSettings
          board={full.board}
          onBoardChange={(b) => setFull((cur) => (cur ? { ...cur, board: b } : cur))}
        />
      )}

      <div className="flex flex-1 gap-3 overflow-x-auto">
        {columns.map((col, i) => (
          <section
            key={col.id}
            aria-label={col.name}
            className="flex w-64 shrink-0 flex-col gap-2 rounded bg-zinc-900/60 p-2"
          >
            <h2 className="px-1 text-sm font-medium text-zinc-300">
              {col.name}
              {col.wip_limit != null && (
                <span className="ml-1 text-xs text-zinc-500">
                  ({cardsOf(full?.cards ?? [], col.id).length}/{col.wip_limit})
                </span>
              )}
            </h2>
            {cardsOf(full?.cards ?? [], col.id).map((card) => (
              <article key={card.id} className="rounded bg-zinc-800 p-2 text-sm text-zinc-100">
                <button
                  type="button"
                  className="block w-full text-left hover:text-indigo-300"
                  onClick={() => setOpenCardId(card.id)}
                >
                  {card.title}
                </button>
                <div className="mt-1 flex justify-between text-xs text-zinc-400">
                  <span>{card.assignee ?? ""}</span>
                  <span className="flex gap-2">
                    {i > 0 && (
                      <button
                        type="button"
                        aria-label={`Mover ${card.title} para ${columns[i - 1].name}`}
                        onClick={() => moveTo(card, columns[i - 1].id)}
                      >
                        ←
                      </button>
                    )}
                    {i < columns.length - 1 && (
                      <button
                        type="button"
                        aria-label={`Mover ${card.title} para ${columns[i + 1].name}`}
                        onClick={() => moveTo(card, columns[i + 1].id)}
                      >
                        →
                      </button>
                    )}
                  </span>
                </div>
              </article>
            ))}
            {col.is_landing && (
              <div className="mt-1 flex gap-1">
                <input
                  aria-label="Novo card"
                  className="min-w-0 flex-1 rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
                  placeholder="Novo card…"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && createCard()}
                />
                <button
                  type="button"
                  className="rounded bg-indigo-600 px-2 text-sm text-white"
                  onClick={createCard}
                >
                  +
                </button>
              </div>
            )}
          </section>
        ))}
      </div>

      {openCard && <CardDetail card={openCard} onClose={() => setOpenCardId(null)} />}
    </div>
  );
}

function CreateFirstBoard({ onCreated }: { onCreated: (b: KanbanBoard) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function create() {
    if (!name.trim()) return;
    try {
      onCreated(await kanbanApi.createBoard({ name: name.trim() }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao criar o quadro.");
    }
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-300">
      <p>Você ainda não tem um quadro.</p>
      <div className="flex gap-2">
        <input
          aria-label="Nome do quadro"
          className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
          placeholder="Nome do quadro"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          type="button"
          className="rounded bg-indigo-600 px-3 py-1 text-sm text-white"
          onClick={create}
        >
          Criar quadro
        </button>
      </div>
      {error && <p className="text-sm text-red-400">{error}</p>}
    </div>
  );
}
