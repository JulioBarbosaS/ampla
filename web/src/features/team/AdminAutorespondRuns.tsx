import { useCallback, useEffect, useState } from "react";
import { adminApi } from "../../lib/api/admin";
import type { AutorespondRun } from "../../lib/api/types";
import { RunRow } from "../agents/AutorespondRuns";

/**
 * Instance-wide auto-respond transcript (admin oversight). The per-agent view
 * lives on each AgentCard; this is the cross-agent feed of GET
 * /api/admin/autorespond-runs, so an admin can watch every agent's automatic
 * activity in one place. Each row shows which agent ran.
 */
export function AdminAutorespondRuns() {
  const [runs, setRuns] = useState<AutorespondRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setError(null);
    setLoading(true);
    adminApi
      .autorespondRuns()
      .then(setRuns)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">Atividade automática (todos)</h2>
          <p className="text-xs text-zinc-500">
            Respostas automáticas de <strong>todos</strong> os agentes da instância — a trilha
            auditável do auto-respond.
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
        {loading && runs === null && <p className="text-xs text-zinc-500">carregando…</p>}
        {runs?.length === 0 && (
          <p className="text-xs text-zinc-500">Nenhuma resposta automática registrada ainda.</p>
        )}
        {runs && runs.length > 0 && (
          <ul className="space-y-1.5">
            {runs.map((run) => (
              <RunRow key={run.id} run={run} showAgent />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
