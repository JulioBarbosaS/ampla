import { useState } from "react";
import { agentsApi } from "../../lib/api/agents";
import type { EscalateOutcome } from "../../lib/api/types";

/** The auto-respond outcomes the owner can route to their Inbox (Epic 04 · 4.3),
 * with pt-BR labels. The `__ESCALATE__` sentinel always escalates and is not in
 * this list (not configurable). */
const OUTCOMES: { key: EscalateOutcome; label: string }[] = [
  { key: "failed", label: "Falhou" },
  { key: "blocked", label: "Bloqueado (filtro)" },
  { key: "rate_limited", label: "Limite/hora" },
  { key: "budget_exceeded", label: "Orçamento" },
  { key: "outside_hours", label: "Fora do horário" },
];

/** Escalation editor (Epic 04 · 4.3): pick which non-answers reach the owner's
 * Inbox. Saves on its own (escalate_on is a list, not a flat field of the main
 * settings form). Empty selection disables escalation. */
export function AgentEscalation({
  slug,
  escalateOn,
  onChanged,
}: {
  slug: string;
  escalateOn: EscalateOutcome[];
  onChanged: () => void;
}) {
  const [selected, setSelected] = useState<Set<EscalateOutcome>>(new Set(escalateOn));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function toggle(key: EscalateOutcome) {
    setSaved(false);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function save() {
    setError(null);
    setSaved(false);
    try {
      // preserve the canonical order so the field round-trips predictably
      const escalate_on = OUTCOMES.map((o) => o.key).filter((k) => selected.has(k));
      await agentsApi.updateSettings(slug, { escalate_on });
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar escalação.");
    }
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <p className="text-sm font-medium text-zinc-300">
        Escalar para minha inbox quando a auto-resposta…
      </p>
      <p className="mt-0.5 text-xs text-zinc-500">
        Sem nenhum marcado, nada é escalado. O agente sempre pode encaminhar manualmente respondendo{" "}
        <code className="text-zinc-400">__ESCALATE__</code>.
      </p>
      <div className="mt-2 flex flex-wrap gap-1">
        {OUTCOMES.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => toggle(o.key)}
            aria-pressed={selected.has(o.key)}
            className={`rounded px-2 py-0.5 text-xs ${
              selected.has(o.key) ? "bg-emerald-800 text-emerald-100" : "bg-zinc-800 text-zinc-400"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
        >
          Salvar escalação
        </button>
        {saved && <span className="text-xs text-emerald-400">salvo ✓</span>}
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
