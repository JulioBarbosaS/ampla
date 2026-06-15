import { useState } from "react";
import { agentsApi } from "../../lib/api/agents";
import type { AutoSchedule } from "../../lib/api/types";

const DAYS: { n: number; label: string }[] = [
  { n: 1, label: "Seg" },
  { n: 2, label: "Ter" },
  { n: 3, label: "Qua" },
  { n: 4, label: "Qui" },
  { n: 5, label: "Sex" },
  { n: 6, label: "Sáb" },
  { n: 7, label: "Dom" },
];

function browserTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** Availability window / DND editor (Epic 04 · 4.2). One window (days + hours +
 * tz); off = always-on. Saves on its own (the schedule is an array, not a flat
 * field of the main settings form). v1 edits the first window if several exist. */
export function AgentSchedule({
  slug,
  schedule,
  onChanged,
}: {
  slug: string;
  schedule: AutoSchedule | null;
  onChanged: () => void;
}) {
  const first = schedule?.windows[0];
  const [enabled, setEnabled] = useState(schedule != null);
  const [days, setDays] = useState<Set<number>>(new Set(first?.days ?? [1, 2, 3, 4, 5]));
  const [start, setStart] = useState(first?.start ?? "09:00");
  const [end, setEnd] = useState(first?.end ?? "18:00");
  const [tz, setTz] = useState(schedule?.tz ?? browserTz());
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function touch() {
    setSaved(false);
  }

  function toggleDay(n: number) {
    touch();
    setDays((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  }

  async function save() {
    setError(null);
    setSaved(false);
    if (enabled) {
      if (days.size === 0) return setError("Selecione ao menos um dia.");
      if (start >= end) return setError("O início deve ser antes do fim.");
    }
    try {
      if (enabled) {
        await agentsApi.updateSettings(slug, {
          auto_schedule: { tz, windows: [{ days: [...days].sort((a, b) => a - b), start, end }] },
        });
      } else {
        await agentsApi.updateSettings(slug, { clear_auto_schedule: true });
      }
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao salvar horário.");
    }
  }

  return (
    <div className="mt-4 border-t border-zinc-800 pt-3">
      <label className="flex items-center gap-2 text-sm font-medium text-zinc-300">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => {
            setEnabled(e.target.checked);
            touch();
          }}
          className="accent-emerald-500"
        />
        Auto-resposta só em horário (fora dele, vai pra inbox)
      </label>
      {enabled && (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-1">
            {DAYS.map((d) => (
              <button
                key={d.n}
                type="button"
                onClick={() => toggleDay(d.n)}
                aria-pressed={days.has(d.n)}
                className={`rounded px-2 py-0.5 text-xs ${
                  days.has(d.n) ? "bg-emerald-800 text-emerald-100" : "bg-zinc-800 text-zinc-400"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            <label className="flex items-center gap-1">
              das
              <input
                type="time"
                aria-label="Início"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  touch();
                }}
                className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-zinc-100"
              />
            </label>
            <label className="flex items-center gap-1">
              às
              <input
                type="time"
                aria-label="Fim"
                value={end}
                onChange={(e) => {
                  setEnd(e.target.value);
                  touch();
                }}
                className="rounded border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-zinc-100"
              />
            </label>
          </div>
          <label className="block text-xs text-zinc-400">
            Fuso (IANA)
            <input
              aria-label="Fuso horário"
              value={tz}
              onChange={(e) => {
                setTz(e.target.value);
                touch();
              }}
              className="mt-1 block w-full rounded border border-zinc-700 bg-zinc-900 px-1.5 py-1 text-zinc-100"
            />
          </label>
        </div>
      )}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-700"
        >
          Salvar horário
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
