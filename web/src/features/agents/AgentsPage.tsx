import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Field, FormError } from "../../components/forms";
import { agentsApi } from "../../lib/api/agents";
import { groupsApi } from "../../lib/api/groups";
import type { Agent, Group } from "../../lib/api/types";
import { AgentCard } from "./AgentCard";

export function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [online, setOnline] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    agentsApi
      .mine()
      .then(setAgents)
      .catch(() => {});
  }, []);

  const reloadGroups = useCallback(() => {
    groupsApi
      .list()
      .then(setGroups)
      .catch(() => {});
  }, []);

  useEffect(() => {
    reload();
    reloadGroups();
    agentsApi
      .directory()
      .then((dir) => setOnline(Object.fromEntries(dir.map((d) => [d.slug, d.online]))))
      .catch(() => {});
  }, [reload, reloadGroups]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(null);
    try {
      await agentsApi.create({
        slug: String(data.get("slug")).trim(),
        display_name: String(data.get("display_name")).trim(),
      });
      form.reset();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar agente.");
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-6 overflow-y-auto px-4 py-6">
      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Criar agente</h2>
        <form onSubmit={handleCreate} className="flex items-end gap-2">
          <div className="flex-1">
            <Field
              label="Slug (ex: backend-julio)"
              name="slug"
              required
              pattern="[a-z][a-z0-9-]{1,48}[a-z0-9]"
              title="kebab-case: letras minúsculas, números e hífens"
            />
          </div>
          <div className="flex-1">
            <Field label="Nome de exibição" name="display_name" required maxLength={120} />
          </div>
          <button
            type="submit"
            className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500"
          >
            Criar
          </button>
        </form>
        <div className="mt-2">
          <FormError message={error} />
        </div>
      </section>

      {agents.map((agent) => (
        <AgentCard
          key={agent.slug}
          agent={agent}
          online={online[agent.slug] ?? false}
          groups={groups}
          onChanged={reload}
          onGroupsChanged={reloadGroups}
        />
      ))}
      {agents.length === 0 && (
        <p className="text-center text-sm text-zinc-500">
          Nenhum agente seu ainda — crie o primeiro acima.
        </p>
      )}
    </div>
  );
}
