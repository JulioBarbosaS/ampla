import { useCallback, useEffect, useState } from "react";
import { adminApi } from "../../lib/api/admin";
import type { InstanceMetrics as Metrics } from "../../lib/api/types";

const WINDOWS = [7, 30, 90];

const RESULT_CLS: Record<string, string> = {
  replied: "bg-emerald-950/50 text-emerald-300",
  blocked: "bg-red-950/50 text-red-300",
  failed: "bg-amber-950/50 text-amber-300",
  skipped: "bg-zinc-800 text-zinc-400",
};

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md bg-zinc-900 px-3 py-2">
      <div className="text-lg font-semibold text-zinc-100">{value}</div>
      <div className="text-xs text-zinc-500">{label}</div>
      {hint && <div className="text-[11px] text-zinc-600">{hint}</div>}
    </div>
  );
}

/** A tiny dependency-free bar chart: one bar per day, height ∝ runs. */
function DailyBars({ daily }: { daily: Metrics["autorespond_daily"] }) {
  const max = Math.max(1, ...daily.map((d) => d.runs));
  return (
    <div className="flex items-end gap-1" style={{ height: 64 }}>
      {daily.map((d) => (
        <div
          key={d.date}
          className="min-w-1.5 flex-1 rounded-t bg-indigo-500/70"
          style={{ height: `${Math.max(4, (d.runs / max) * 100)}%` }}
          title={`${d.date}: ${d.runs} execuçõe(s), $${d.cost_usd.toFixed(4)}`}
        />
      ))}
    </div>
  );
}

/**
 * Instance observability (admin-only). A windowed roll-up of auto-respond
 * cost/result, message throughput and audit activity — the aggregate view the
 * per-agent transcript and the raw audit log don't give on their own.
 */
export function InstanceMetrics() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback((window: number) => {
    setError(null);
    setLoading(true);
    adminApi
      .metrics(window)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => load(days), [days, load]);

  const ar = data?.autorespond;
  return (
    <section className="rounded-lg border border-zinc-800 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-200">Métricas da instância</h2>
          <p className="text-xs text-zinc-500">
            Custo e resultado das auto-respostas, throughput de mensagens e atividade — agregados na
            janela.
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-zinc-500">
          Janela:
          <select
            aria-label="Janela de tempo"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-1.5 py-1 text-xs text-zinc-200"
          >
            {WINDOWS.map((w) => (
              <option key={w} value={w}>
                {w} dias
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-3">
        {error && (
          <p role="alert" className="text-xs text-red-400">
            {error}
          </p>
        )}
        {loading && data === null && <p className="text-xs text-zinc-500">carregando…</p>}
        {data && ar && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              <Stat label="Mensagens" value={String(data.messages_total)} />
              <Stat label="Auto-respostas" value={String(ar.total_runs)} />
              <Stat label="Custo" value={`$${ar.total_cost_usd.toFixed(2)}`} />
              <Stat label="Timeouts" value={String(ar.timed_out)} />
              <Stat
                label="Duração média"
                value={`${(ar.avg_duration_ms / 1000).toFixed(1)}s`}
                hint={`${ar.total_output_tokens} tokens de saída`}
              />
            </div>

            {Object.keys(ar.by_result).length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-zinc-500">Resultado:</span>
                {Object.entries(ar.by_result).map(([result, count]) => (
                  <span
                    key={result}
                    className={`rounded px-1.5 py-0.5 font-medium ${
                      RESULT_CLS[result] ?? "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {result} · {count}
                  </span>
                ))}
              </div>
            )}

            {data.autorespond_daily.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-zinc-500">Auto-respostas por dia</div>
                <DailyBars daily={data.autorespond_daily} />
              </div>
            )}

            {data.audit_events.length > 0 && (
              <div>
                <div className="mb-1 text-xs text-zinc-500">Eventos auditados na janela</div>
                <ul className="flex flex-wrap gap-1.5 text-xs">
                  {data.audit_events.map((e) => (
                    <li
                      key={e.event}
                      className="rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-zinc-400"
                    >
                      {e.event} · <span className="text-zinc-200">{e.count}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
