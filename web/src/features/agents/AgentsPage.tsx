import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Field, FormError } from "../../components/forms";
import { agentsApi } from "../../lib/api/agents";
import { authApi } from "../../lib/api/auth";
import { groupsApi } from "../../lib/api/groups";
import type { Agent, Group } from "../../lib/api/types";
import { useAuthStore } from "../../stores/auth";
import { AgentCard } from "./AgentCard";

export function AgentsPage() {
  const user = useAuthStore((s) => s.user);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [online, setOnline] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [inviteLink, setInviteLink] = useState<string | null>(null);

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

  async function handleInvite() {
    setError(null);
    try {
      const invite = await authApi.createInvite();
      setInviteLink(`${window.location.origin}/register?code=${invite.code}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar convite.");
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-6 overflow-y-auto px-4 py-6">
      {user?.role === "admin" && (
        <section className="rounded-lg border border-zinc-800 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-zinc-200">Convidar membro da equipe</h2>
              <p className="text-xs text-zinc-500">
                Gera um link de uso único (expira em 48h). Envie por onde preferir.
              </p>
            </div>
            <button
              type="button"
              onClick={handleInvite}
              className="rounded-md bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-200 hover:bg-zinc-700"
            >
              Gerar convite
            </button>
          </div>
          {inviteLink && (
            <p className="mt-3 break-all rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs text-emerald-300">
              {inviteLink}
            </p>
          )}
        </section>
      )}

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
