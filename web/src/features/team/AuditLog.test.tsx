import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditEntry } from "../../lib/api/types";
import { usersApi } from "../../lib/api/users";
import { AuditLog } from "./AuditLog";

vi.mock("../../lib/api/users", () => ({ usersApi: { auditLog: vi.fn() } }));

const ENTRIES: AuditEntry[] = [
  {
    id: 2,
    event: "kanban_member_added",
    actor: "admin@amp.local",
    detail: { board_id: 1, user_id: 7 },
    created_at: "2026-06-23T10:05:00Z",
  },
  {
    id: 1,
    event: "kanban_board_created",
    actor: "admin@amp.local",
    detail: null,
    created_at: "2026-06-23T10:00:00Z",
  },
];

beforeEach(() => vi.mocked(usersApi.auditLog).mockResolvedValue(ENTRIES));
afterEach(() => vi.clearAllMocks());

describe("AuditLog", () => {
  it("renders the audit trail with actor + detail", async () => {
    render(<AuditLog />);
    expect(await screen.findByText("kanban_member_added")).toBeInTheDocument();
    expect(screen.getByText("kanban_board_created")).toBeInTheDocument();
    // the detail object is shown for the entry that has one
    expect(screen.getByText(/"board_id":1/)).toBeInTheDocument();
    expect(usersApi.auditLog).toHaveBeenCalled();
  });

  it("shows an empty state when there are no events", async () => {
    vi.mocked(usersApi.auditLog).mockResolvedValue([]);
    render(<AuditLog />);
    expect(await screen.findByText(/Nenhum evento registrado/)).toBeInTheDocument();
  });
});
