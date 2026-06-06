import { useEffect, useState } from "react";
import { agentsApi } from "../../lib/api/agents";
import type { Agent } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";

export function PresenceDot({ online }: { online: boolean }) {
  return (
    <span
      role="img"
      aria-label={online ? "online" : "offline"}
      className={`inline-block h-2.5 w-2.5 rounded-full ${
        online ? "bg-emerald-500" : "bg-zinc-600"
      }`}
    />
  );
}

export function Sidebar() {
  const { perspective, partner, directory, online } = useChatStore();
  const setPerspective = useChatStore((s) => s.setPerspective);
  const setPartner = useChatStore((s) => s.setPartner);
  const [mine, setMine] = useState<Agent[]>([]);

  useEffect(() => {
    agentsApi
      .mine()
      .then(setMine)
      .catch(() => {});
  }, []);

  const others = directory.filter((entry) => entry.slug !== perspective);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-zinc-800">
      <div className="border-b border-zinc-800 p-3">
        <label
          htmlFor="perspective-select"
          className="mb-1 block text-xs uppercase tracking-wide text-zinc-500"
        >
          Conversando como
        </label>
        <select
          id="perspective-select"
          value={perspective ?? ""}
          onChange={(event) => setPerspective(event.target.value || null)}
          className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm outline-none focus:border-emerald-500"
        >
          <option value="">— selecione um agente —</option>
          {mine.map((agent) => (
            <option key={agent.slug} value={agent.slug}>
              {agent.slug}
            </option>
          ))}
        </select>
        {mine.length === 0 && (
          <p className="mt-2 text-xs text-zinc-500">
            Você ainda não tem agentes. Crie um em “Meus agentes”.
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="px-3 pb-1 pt-3 text-xs uppercase tracking-wide text-zinc-500">Equipe</p>
        <ul>
          {others.map((entry) => (
            <li key={entry.slug}>
              <button
                type="button"
                onClick={() => setPartner(entry.slug)}
                className={`flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-zinc-900 ${
                  partner === entry.slug ? "bg-zinc-900" : ""
                }`}
              >
                <PresenceDot online={online[entry.slug] ?? false} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-zinc-200">{entry.slug}</span>
                  <span className="block truncate text-xs text-zinc-500">{entry.display_name}</span>
                </span>
              </button>
            </li>
          ))}
          {others.length === 0 && (
            <li className="px-3 py-2 text-sm text-zinc-500">Nenhum outro agente na equipe.</li>
          )}
        </ul>
      </div>
    </aside>
  );
}
