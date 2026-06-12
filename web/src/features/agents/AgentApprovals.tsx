import { useState } from "react";
import { Markdown } from "../../components/Markdown";
import { agentsApi } from "../../lib/api/agents";
import type { Approval } from "../../lib/api/types";

type Decide = (id: number, decision: "approve" | "reject", body?: string) => void;

function ApprovalRow({ approval, onDecide }: { approval: Approval; onDecide: Decide }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(approval.draft_body);

  return (
    <li className="space-y-2 rounded-md bg-zinc-900 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-red-900/50 px-1.5 py-0.5 font-medium text-red-300">
          aprovação
        </span>
        <span className="text-zinc-400">
          resposta para <span className="font-mono text-zinc-300">{approval.to_agent}</span>
        </span>
        <span className="ml-auto text-zinc-600">
          {new Date(approval.created_at).toLocaleString("pt-BR")}
        </span>
      </div>
      {editing ? (
        <textarea
          aria-label="Editar rascunho"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={4}
          className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 font-mono text-[11px] text-zinc-100"
        />
      ) : (
        // Agent-authored draft — rendered as sanitized Markdown (no raw HTML).
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-2 py-1.5 text-zinc-200">
          <Markdown>{approval.draft_body}</Markdown>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-1.5">
        {editing ? (
          <>
            <button
              type="button"
              onClick={() => onDecide(approval.id, "approve", draft)}
              className="rounded bg-zinc-800 px-2 py-0.5 text-emerald-300 hover:bg-zinc-700"
            >
              Enviar editado
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded px-2 py-0.5 text-zinc-400 hover:text-zinc-200"
            >
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onDecide(approval.id, "approve")}
              className="rounded bg-zinc-800 px-2 py-0.5 text-emerald-300 hover:bg-zinc-700"
            >
              Aprovar
            </button>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-300 hover:bg-zinc-700"
            >
              Editar e enviar
            </button>
            <button
              type="button"
              onClick={() => onDecide(approval.id, "reject")}
              className="rounded bg-zinc-800 px-2 py-0.5 text-zinc-400 hover:bg-zinc-700"
            >
              Rejeitar
            </button>
          </>
        )}
      </div>
    </li>
  );
}

/** "Pendências de aprovação": drafts this agent is holding for the owner's
 * decision (Epic 03 · 3.3). Collapsed by default; lazy-loads on first open. */
export function AgentApprovals({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function load() {
    setError(null);
    setLoading(true);
    agentsApi
      .approvals(slug)
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && items === null && !loading) load();
  }

  async function decide(id: number, decision: "approve" | "reject", body?: string) {
    setError(null);
    try {
      await agentsApi.decideApproval(id, decision, body);
      // the thread leaves the pending list either way (approved/edited/rejected)
      setItems((prev) => (prev ? prev.filter((a) => a.id !== id) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao decidir.");
    }
  }

  const count = items?.length ?? 0;
  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={toggle}
          className="flex items-center gap-1.5 text-sm font-medium text-zinc-300 hover:text-zinc-100"
          aria-expanded={open}
        >
          <span className="text-zinc-500">{open ? "▾" : "▸"}</span> Pendências de aprovação
          {count > 0 && (
            <span className="rounded-full bg-red-900/60 px-1.5 text-[10px] text-red-200">
              {count}
            </span>
          )}
        </button>
        {open && (
          <button
            type="button"
            onClick={load}
            className="rounded-md bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Atualizar
          </button>
        )}
      </div>
      {open && (
        <div className="mt-2">
          {error && (
            <p role="alert" className="text-xs text-red-400">
              {error}
            </p>
          )}
          {loading && items === null && <p className="text-xs text-zinc-500">carregando…</p>}
          {items?.length === 0 && (
            <p className="text-xs text-zinc-500">Nenhuma resposta aguardando aprovação.</p>
          )}
          {items && items.length > 0 && (
            <ul className="space-y-1.5">
              {items.map((a) => (
                <ApprovalRow key={a.id} approval={a} onDecide={decide} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
