import { useCallback, useEffect, useState } from "react";
import type { AuditEntry } from "../../lib/api/types";
import { usersApi } from "../../lib/api/users";

/** Group an event like "kanban_grant_set" into a coarse family for chip color. */
function family(event: string): "security" | "delete" | "create" | "other" {
  if (/(grant|member|role|kill|reset|password|approval|escalat)/.test(event)) return "security";
  if (event.includes("deleted") || event.includes("removed")) return "delete";
  if (event.includes("created") || event.includes("added")) return "create";
  return "other";
}

const FAMILY_CLS: Record<ReturnType<typeof family>, string> = {
  security: "bg-red-950/50 text-red-300",
  delete: "bg-amber-950/50 text-amber-300",
  create: "bg-emerald-950/50 text-emerald-300",
  other: "bg-zinc-800 text-zinc-400",
};

function AuditRow({ entry }: { entry: AuditEntry }) {
  const cls = FAMILY_CLS[family(entry.event)];
  const detail = entry.detail && Object.keys(entry.detail).length > 0 ? entry.detail : null;
  return (
    <li className="space-y-1 rounded-md bg-zinc-900 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 font-mono font-medium ${cls}`}>{entry.event}</span>
        <span className="text-zinc-400">
          por <span className="font-mono text-zinc-300">{entry.actor || "—"}</span>
        </span>
        <span className="ml-auto text-zinc-600">
          {new Date(entry.created_at).toLocaleString("pt-BR")}
        </span>
      </div>
      {detail && (
        <p className="whitespace-pre-wrap break-words font-mono text-[11px] text-zinc-500">
          {JSON.stringify(detail)}
        </p>
      )}
    </li>
  );
}

/**
 * Instance audit trail (admin-only). Every mutation across the hub records an
 * audit event; this is the only place to review them (GET /api/users/audit).
 * Newest first.
 */
export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setError(null);
    setLoading(true);
    usersApi
      .auditLog()
      .then(setEntries)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">Log de auditoria</h2>
          <p className="text-xs text-zinc-500">
            Cada ação sensível na instância é registrada aqui — quem fez o quê e quando.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
        >
          Atualizar
        </button>
      </div>
      <div className="mt-3">
        {error && (
          <p role="alert" className="text-xs text-red-400">
            {error}
          </p>
        )}
        {loading && entries === null && <p className="text-xs text-zinc-500">carregando…</p>}
        {entries?.length === 0 && (
          <p className="text-xs text-zinc-500">Nenhum evento registrado ainda.</p>
        )}
        {entries && entries.length > 0 && (
          <ul className="space-y-1.5">
            {entries.map((entry) => (
              <AuditRow key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
