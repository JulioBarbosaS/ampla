import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../lib/api/client";
import { cardsOf, kanbanApi, sortColumns } from "../../lib/api/kanban";
import type { KanbanBoard, KanbanBoardFull, KanbanCard, KanbanColumn } from "../../lib/api/types";
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
  const [newBoardName, setNewBoardName] = useState("");
  const [showNewBoard, setShowNewBoard] = useState(false);
  const [newColumnName, setNewColumnName] = useState("");
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

  async function applyMove(
    card: KanbanCard,
    toColumnId: number,
    beforeId?: number,
    afterId?: number,
  ) {
    if (boardId === null) return;
    const previous = full;
    // optimistic: reflect the destination column right away
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
        ...(beforeId !== undefined ? { before_id: beforeId } : {}),
        ...(afterId !== undefined ? { after_id: afterId } : {}),
        expected_version: card.version,
      });
      // replacing with the server card (fresh rank) re-sorts it into place
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

  /** Reorder a card up/down within its column using the anchor-based API. */
  function reorder(card: KanbanCard, dir: -1 | 1) {
    if (!full) return;
    const col = cardsOf(full.cards, card.column_id);
    const i = col.findIndex((c) => c.id === card.id);
    const j = i + dir;
    if (j < 0 || j >= col.length) return;
    // moving up: land between the card two-up and the one-up; down: mirror.
    const [before, after] = dir < 0 ? [col[j - 1], col[j]] : [col[j], col[j + 1]];
    applyMove(card, card.column_id, before?.id, after?.id);
  }

  async function addBoard() {
    if (!newBoardName.trim()) return;
    try {
      const b = await kanbanApi.createBoard({ name: newBoardName.trim() });
      setNewBoardName("");
      setShowNewBoard(false);
      setBoards((cur) => [...(cur ?? []), b]);
      setBoardId(b.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao criar o quadro.");
    }
  }

  async function addColumn() {
    if (boardId === null || !newColumnName.trim()) return;
    setNewColumnName("");
    try {
      await kanbanApi.createColumn(boardId, { name: newColumnName.trim() });
      reload(boardId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao criar a coluna.");
    }
  }

  async function patchColumn(
    columnId: number,
    data: { name?: string; wip_limit?: number; is_landing?: boolean },
  ) {
    if (boardId === null) return;
    try {
      await kanbanApi.updateColumn(boardId, columnId, data);
      reload(boardId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao atualizar a coluna.");
    }
  }

  async function removeColumn(columnId: number) {
    if (boardId === null) return;
    try {
      await kanbanApi.deleteColumn(boardId, columnId);
      reload(boardId);
    } catch (e) {
      // backend refuses a non-empty or landing column (409) — surface the reason
      setError(e instanceof Error ? e.message : "Falha ao remover a coluna.");
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
        <span className="ml-auto flex items-center gap-2">
          {showNewBoard ? (
            <>
              <input
                aria-label="Nome do novo quadro"
                className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
                placeholder="Nome do quadro"
                value={newBoardName}
                onChange={(e) => setNewBoardName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addBoard()}
              />
              <button
                type="button"
                className="rounded bg-indigo-600 px-2 py-1 text-sm text-white"
                onClick={addBoard}
              >
                Criar
              </button>
            </>
          ) : (
            <button
              type="button"
              className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
              onClick={() => setShowNewBoard(true)}
            >
              + Novo quadro
            </button>
          )}
          {canManage && (
            <button
              type="button"
              className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-300 hover:bg-zinc-700"
              onClick={() => setShowSettings((s) => !s)}
            >
              Permissões
            </button>
          )}
        </span>
      </header>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {showSettings && canManage && full && (
        <BoardSettings
          board={full.board}
          onBoardChange={(b) => setFull((cur) => (cur ? { ...cur, board: b } : cur))}
          onBoardDeleted={() => {
            const deletedId = full.board.id;
            const remaining = (boards ?? []).filter((b) => b.id !== deletedId);
            setBoards(remaining);
            setShowSettings(false);
            setFull(null);
            setBoardId(remaining[0]?.id ?? null);
          }}
        />
      )}

      <div className="flex flex-1 gap-3 overflow-x-auto">
        {columns.map((col, i) => {
          const colCards = cardsOf(full?.cards ?? [], col.id);
          return (
            <section
              key={col.id}
              aria-label={col.name}
              className="flex w-64 shrink-0 flex-col gap-2 rounded bg-zinc-900/60 p-2"
            >
              <ColumnHeader
                column={col}
                count={colCards.length}
                onRename={(name) => patchColumn(col.id, { name })}
                onSetLanding={() => patchColumn(col.id, { is_landing: true })}
                onSetWip={(wip) => patchColumn(col.id, { wip_limit: wip })}
                onDelete={() => removeColumn(col.id)}
              />
              {colCards.map((card, ci) => (
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
                      {ci > 0 && (
                        <button
                          type="button"
                          aria-label={`Subir ${card.title}`}
                          onClick={() => reorder(card, -1)}
                        >
                          ↑
                        </button>
                      )}
                      {ci < colCards.length - 1 && (
                        <button
                          type="button"
                          aria-label={`Descer ${card.title}`}
                          onClick={() => reorder(card, 1)}
                        >
                          ↓
                        </button>
                      )}
                      {i > 0 && (
                        <button
                          type="button"
                          aria-label={`Mover ${card.title} para ${columns[i - 1].name}`}
                          onClick={() => applyMove(card, columns[i - 1].id)}
                        >
                          ←
                        </button>
                      )}
                      {i < columns.length - 1 && (
                        <button
                          type="button"
                          aria-label={`Mover ${card.title} para ${columns[i + 1].name}`}
                          onClick={() => applyMove(card, columns[i + 1].id)}
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
          );
        })}

        <div className="flex w-56 shrink-0 flex-col gap-1">
          <input
            aria-label="Nova coluna"
            className="rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
            placeholder="+ Nova coluna…"
            value={newColumnName}
            onChange={(e) => setNewColumnName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addColumn()}
          />
        </div>
      </div>

      {openCard && (
        <CardDetail
          card={openCard}
          onClose={() => setOpenCardId(null)}
          onChanged={(updated) => {
            setFull((cur) =>
              cur
                ? {
                    ...cur,
                    cards: updated
                      ? cur.cards.map((c) => (c.id === updated.id ? updated : c))
                      : cur.cards.filter((c) => c.id !== openCard.id),
                  }
                : cur,
            );
          }}
        />
      )}
    </div>
  );
}

function ColumnHeader({
  column,
  count,
  onRename,
  onSetLanding,
  onSetWip,
  onDelete,
}: {
  column: KanbanColumn;
  count: number;
  onRename: (name: string) => void;
  onSetLanding: () => void;
  onSetWip: (wip: number) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(column.name);

  function commitRename() {
    setEditing(false);
    const trimmed = name.trim();
    if (trimmed && trimmed !== column.name) onRename(trimmed);
    else setName(column.name);
  }

  return (
    <div className="flex items-center justify-between gap-1 px-1">
      {editing ? (
        <input
          aria-label={`Nome da coluna ${column.name}`}
          className="min-w-0 flex-1 rounded bg-zinc-800 px-1 text-sm text-zinc-100"
          value={name}
          // biome-ignore lint/a11y/noAutofocus: focus the field the user just opened
          autoFocus
          onChange={(e) => setName(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => e.key === "Enter" && commitRename()}
        />
      ) : (
        <button
          type="button"
          aria-label={`Renomear coluna ${column.name}`}
          className="truncate text-sm font-medium text-zinc-300 hover:text-zinc-100"
          onClick={() => setEditing(true)}
        >
          {column.name} <span className="text-xs text-zinc-500">({count})</span>
        </button>
      )}
      <span className="flex shrink-0 items-center gap-1 text-xs text-zinc-500">
        <button
          type="button"
          aria-label={
            column.is_landing
              ? `${column.name} é a coluna de entrada`
              : `Definir ${column.name} como coluna de entrada`
          }
          className={column.is_landing ? "text-amber-400" : "hover:text-zinc-200"}
          onClick={onSetLanding}
          disabled={column.is_landing}
        >
          ★
        </button>
        <input
          aria-label={`Limite WIP da coluna ${column.name}`}
          type="number"
          min={0}
          className="w-10 rounded bg-zinc-800 px-1 text-zinc-300"
          defaultValue={column.wip_limit ?? ""}
          placeholder="WIP"
          onBlur={(e) => {
            const v = Number(e.target.value);
            const next = Number.isFinite(v) && v > 0 ? v : 0;
            if (next !== (column.wip_limit ?? 0)) onSetWip(next);
          }}
        />
        <button
          type="button"
          aria-label={`Excluir coluna ${column.name}`}
          className="hover:text-red-300"
          onClick={onDelete}
        >
          ×
        </button>
      </span>
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
