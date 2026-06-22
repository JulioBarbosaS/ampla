import { describe, expect, it } from "vitest";
import { cardsOf, sortColumns } from "./kanban";
import type { KanbanCard, KanbanColumn } from "./types";

function col(id: number, rank: string): KanbanColumn {
  return {
    id,
    board_id: 1,
    name: `c${id}`,
    rank,
    wip_limit: null,
    is_landing: false,
    is_done: false,
  };
}

function card(id: number, columnId: number, rank: string): KanbanCard {
  return {
    id,
    board_id: 1,
    column_id: columnId,
    rank,
    title: `t${id}`,
    body: "",
    created_by: "user:1",
    assignee: null,
    priority: "normal",
    origin: null,
    version: 1,
    depends_on: [],
    created_at: "",
    updated_at: "",
  };
}

describe("kanban ordering helpers", () => {
  it("sortColumns orders by rank (server's left→right order)", () => {
    const sorted = sortColumns([col(1, "s"), col(2, "a"), col(3, "k")]);
    expect(sorted.map((c) => c.id)).toEqual([2, 3, 1]);
  });

  it("cardsOf filters to a column and sorts by rank", () => {
    const cards = [card(1, 10, "m"), card(2, 20, "a"), card(3, 10, "c")];
    expect(cardsOf(cards, 10).map((c) => c.id)).toEqual([3, 1]);
    expect(cardsOf(cards, 20).map((c) => c.id)).toEqual([2]);
  });
});
