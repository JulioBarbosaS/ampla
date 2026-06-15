import { useState } from "react";
import { agentsApi } from "../../lib/api/agents";
import type { Delegation, DelegationStatus } from "../../lib/api/types";

const STATUS_CHIP: Record<DelegationStatus, { label: string; cls: string }> = {
  open: { label: "aberta", cls: "bg-amber-900/50 text-amber-300" },
  completed: { label: "concluída", cls: "bg-emerald-900/50 text-emerald-300" },
  declined: { label: "recusada", cls: "bg-red-900/50 text-red-300" },
};

function DelegationRow({ delegation, slug }: { delegation: Delegation; slug: string }) {
  const chip = STATUS_CHIP[delegation.status] ?? STATUS_CHIP.open;
  // The card belongs to one agent: show the direction relative to it.
  const outgoing = delegation.from_agent === slug;
  const other = outgoing ? delegation.to_agent : delegation.from_agent;

  return (
    <li className="space-y-1 rounded-md bg-zinc-900 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 font-medium ${chip.cls}`}>{chip.label}</span>
        <span className="text-zinc-400">
          {outgoing ? "para" : "de"} <span className="font-mono text-zinc-300">{other}</span>
        </span>
        <span className="ml-auto text-zinc-600">
          {new Date(delegation.created_at).toLocaleString("pt-BR")}
        </span>
      </div>
      <p className="whitespace-pre-wrap break-words text-zinc-300">{delegation.task}</p>
    </li>
  );
}

/** "Delegações": the agent's task hand-offs, either side (Epic 04 · 4.4).
 * Collapsed by default; lazy-loads on first open. */
export function AgentDelegations({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Delegation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function load() {
    setError(null);
    setLoading(true);
    agentsApi
      .delegations(slug)
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && items === null && !loading) load();
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={toggle}
          className="flex items-center gap-1 text-sm font-medium text-zinc-300 hover:text-zinc-100"
          aria-expanded={open}
        >
          <span className="text-zinc-500">{open ? "▾" : "▸"}</span> Delegações
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
          {items?.length === 0 && <p className="text-xs text-zinc-500">Nenhuma delegação ainda.</p>}
          {items && items.length > 0 && (
            <ul className="space-y-1.5">
              {items.map((d) => (
                <DelegationRow key={d.id} delegation={d} slug={slug} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
