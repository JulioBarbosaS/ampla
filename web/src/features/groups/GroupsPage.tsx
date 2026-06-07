import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Field, FormError } from "../../components/forms";
import { agentsApi } from "../../lib/api/agents";
import { groupsApi } from "../../lib/api/groups";
import type { DirectoryEntry, Group } from "../../lib/api/types";
import { useAuthStore } from "../../stores/auth";
import { PresenceDot } from "../chat/Sidebar";

export function GroupsPage() {
  const user = useAuthStore((s) => s.user);
  const [groups, setGroups] = useState<Group[]>([]);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [mine, setMine] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    groupsApi
      .list()
      .then(setGroups)
      .catch(() => {});
  }, []);

  useEffect(() => {
    reload();
    agentsApi
      .directory()
      .then(setDirectory)
      .catch(() => {});
    agentsApi
      .mine()
      .then((agents) => setMine(new Set(agents.map((a) => a.slug))))
      .catch(() => {});
  }, [reload]);

  const onlineOf = useMemo(
    () => Object.fromEntries(directory.map((d) => [d.slug, d.online])),
    [directory],
  );

  const isAdmin = user?.role === "admin";
  const canAddAgent = useCallback((slug: string) => isAdmin || mine.has(slug), [isAdmin, mine]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(null);
    try {
      await groupsApi.create({
        slug: String(data.get("slug")).trim(),
        display_name: String(data.get("display_name")).trim(),
      });
      form.reset();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar grupo.");
    }
  }

  async function run(action: Promise<unknown>) {
    setError(null);
    try {
      await action;
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operação falhou.");
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-6 overflow-y-auto px-4 py-6">
      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-1 text-sm font-semibold text-zinc-200">Criar grupo</h2>
        <p className="mb-3 text-xs text-zinc-500">
          Qualquer membro pode criar. Use o grupo para transmitir uma mensagem a vários agentes de
          uma vez (<span className="font-mono">@slug</span>).
        </p>
        <form onSubmit={handleCreate} className="flex items-end gap-2">
          <div className="flex-1">
            <Field
              label="Slug (ex: frontend-team)"
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

      {groups.map((group) => {
        const canManage = isAdmin || user?.id === group.created_by;
        const candidates = directory.filter((d) => !group.members.includes(d.slug));
        return (
          <section key={group.slug} className="rounded-lg border border-zinc-800 p-4">
            <header className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="font-mono text-sm font-semibold text-emerald-300">@{group.slug}</h3>
                <p className="text-xs text-zinc-500">{group.display_name}</p>
              </div>
              {canManage && (
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Remover o grupo @${group.slug}?`)) {
                      run(groupsApi.remove(group.slug));
                    }
                  }}
                  className="rounded-md px-2 py-1 text-xs text-red-400 hover:bg-red-950/40 hover:text-red-300"
                >
                  Remover grupo
                </button>
              )}
            </header>

            <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
              Membros ({group.members.length})
            </p>
            <ul className="space-y-1">
              {group.members.map((slug) => (
                <li
                  key={slug}
                  className="flex items-center justify-between rounded-md bg-zinc-900 px-3 py-1.5 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <PresenceDot online={onlineOf[slug] ?? false} />
                    <span className="font-mono text-zinc-300">{slug}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => run(groupsApi.removeMember(group.slug, slug))}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    remover
                  </button>
                </li>
              ))}
              {group.members.length === 0 && (
                <li className="text-xs text-zinc-500">Nenhum membro ainda.</li>
              )}
            </ul>

            {candidates.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
                  Adicionar agente
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {candidates.map((agent) => {
                    const allowed = canAddAgent(agent.slug);
                    return (
                      <button
                        key={agent.slug}
                        type="button"
                        disabled={!allowed}
                        title={
                          allowed
                            ? `adicionar ${agent.slug}`
                            : "só o dono pode adicionar este agente"
                        }
                        onClick={() => run(groupsApi.addMember(group.slug, agent.slug))}
                        className="rounded-full border border-zinc-700 px-2.5 py-1 font-mono text-xs text-zinc-300 enabled:hover:border-emerald-500 enabled:hover:text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        + {agent.slug}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        );
      })}

      {groups.length === 0 && (
        <p className="text-center text-sm text-zinc-500">
          Nenhum grupo ainda — crie o primeiro acima para começar a transmitir.
        </p>
      )}
    </div>
  );
}
