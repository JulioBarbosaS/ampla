import { useState } from "react";
import { agentsApi } from "../../lib/api/agents";
import type { AutorespondRun } from "../../lib/api/types";

/** Result → chip styling. The transcript is an audit surface, so each outcome
 * reads at a glance: replied (ok), blocked (security), failed, skipped. */
const RESULT_CHIP: Record<AutorespondRun["result"], { label: string; cls: string }> = {
  replied: { label: "respondeu", cls: "bg-emerald-900/50 text-emerald-300" },
  blocked: { label: "bloqueado", cls: "bg-red-900/50 text-red-300" },
  failed: { label: "falhou", cls: "bg-amber-900/50 text-amber-300" },
  skipped: { label: "pulado", cls: "bg-zinc-800 text-zinc-400" },
};

function bool(value: unknown): boolean {
  return value === true;
}

/** A small flag badge for the guardrail snapshot. */
function Flag({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
        on ? "bg-emerald-950/60 text-emerald-300" : "bg-zinc-800 text-zinc-500"
      }`}
    >
      {label}
    </span>
  );
}

/** Today's aggregate from the loaded runs (Epic 03 · 3.4 metrics). */
function todaySummary(runs: AutorespondRun[]): { runs: number; tokens: number; cost: number } {
  const today = new Date().toDateString();
  let count = 0;
  let tokens = 0;
  let cost = 0;
  for (const r of runs) {
    if (new Date(r.created_at).toDateString() !== today) continue;
    count += 1;
    tokens += (r.input_tokens ?? 0) + (r.output_tokens ?? 0);
    cost += r.cost_usd ?? 0;
  }
  return { runs: count, tokens, cost };
}

function RunRow({ run }: { run: AutorespondRun }) {
  const chip = RESULT_CHIP[run.result] ?? RESULT_CHIP.skipped;
  const g = run.guardrails ?? {};
  const sandbox = typeof g.sandbox === "string" ? g.sandbox : "host";
  const cost = run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : null;
  const tokens =
    run.input_tokens != null || run.output_tokens != null
      ? `${run.input_tokens ?? 0}→${run.output_tokens ?? 0} tok`
      : null;

  return (
    <li className="space-y-1.5 rounded-md bg-zinc-900 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 font-medium ${chip.cls}`}>{chip.label}</span>
        <span className="text-zinc-400">
          de <span className="font-mono text-zinc-300">{run.from_sender}</span>
        </span>
        <span className="text-zinc-500">· {run.duration_ms} ms</span>
        {run.timed_out && <span className="text-amber-400">· timeout</span>}
        {tokens && <span className="text-zinc-500">· {tokens}</span>}
        {cost && <span className="text-zinc-500">· {cost}</span>}
        <span className="ml-auto text-zinc-600">
          {new Date(run.created_at).toLocaleString("pt-BR")}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
            sandbox === "docker"
              ? "bg-emerald-950/60 text-emerald-300"
              : "bg-amber-950/50 text-amber-300"
          }`}
          title="onde o claude -p rodou"
        >
          {sandbox === "docker" ? "sandbox docker" : "host"}
        </span>
        <Flag on={!bool(g.allow_write)} label="só leitura" />
        <Flag on={bool(g.block_sensitive_paths)} label="bloqueia segredos" />
        {bool(g.trusted_sender) && (
          <span className="rounded bg-red-950/50 px-1.5 py-0.5 text-[10px] font-medium text-red-300">
            remetente confiável (acesso total)
          </span>
        )}
      </div>
      {run.reply_preview && (
        <p className="line-clamp-2 whitespace-pre-wrap break-words font-mono text-[11px] text-zinc-400">
          {run.reply_preview}
        </p>
      )}
      {run.reason && <p className="text-zinc-500">motivo: {run.reason}</p>}
    </li>
  );
}

/** "Atividade automática": the auditable transcript of this agent's auto-respond
 * runs (Epic 03 · 3.1). Collapsed by default; lazy-loads on first open. */
export function AutorespondRuns({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<AutorespondRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function load() {
    setError(null);
    setLoading(true);
    agentsApi
      .autorespondRuns(slug)
      .then(setRuns)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar."))
      .finally(() => setLoading(false));
  }

  // Lazy: fetch the first time the section is opened (no effect needed).
  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && runs === null && !loading) load();
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
          <span className="text-zinc-500">{open ? "▾" : "▸"}</span> Atividade automática
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
          {loading && runs === null && <p className="text-xs text-zinc-500">carregando…</p>}
          {runs?.length === 0 && (
            <p className="text-xs text-zinc-500">Nenhuma resposta automática registrada ainda.</p>
          )}
          {runs && runs.length > 0 && (
            <>
              {(() => {
                const s = todaySummary(runs);
                return (
                  <p className="mb-2 text-xs text-zinc-500">
                    Hoje: <span className="text-zinc-300">{s.runs}</span> respostas ·{" "}
                    <span className="text-zinc-300">{s.tokens}</span> tokens ·{" "}
                    <span className="text-zinc-300">${s.cost.toFixed(4)}</span>
                  </p>
                );
              })()}
              <ul className="space-y-1.5">
                {runs.map((run) => (
                  <RunRow key={run.id} run={run} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
