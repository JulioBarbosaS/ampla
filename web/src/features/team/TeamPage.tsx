import { useCallback, useEffect, useState } from "react";
import { FormError } from "../../components/forms";
import { authApi } from "../../lib/api/auth";
import type { Invite, User } from "../../lib/api/types";
import { usersApi } from "../../lib/api/users";
import { useAuthStore } from "../../stores/auth";

/** Estado de um convite, derivado das datas (não há campo no backend). */
function inviteState(invite: Invite): { label: string; cls: string } {
  if (invite.used_at) return { label: "usado", cls: "bg-zinc-700 text-zinc-300" };
  if (new Date(invite.expires_at).getTime() < Date.now()) {
    return { label: "expirado", cls: "bg-red-900/50 text-red-300" };
  }
  return { label: "pendente", cls: "bg-emerald-900/50 text-emerald-300" };
}

export function TeamPage() {
  const me = useAuthStore((s) => s.user);
  const [users, setUsers] = useState<User[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    usersApi
      .list()
      .then(setUsers)
      .catch(() => {});
    authApi
      .listInvites()
      .then(setInvites)
      .catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  async function handleInvite() {
    setError(null);
    try {
      const invite = await authApi.createInvite();
      setInviteLink(`${window.location.origin}/register?code=${invite.code}`);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar convite.");
    }
  }

  async function changeRole(user: User, role: "admin" | "member") {
    setError(null);
    try {
      await usersApi.setRole(user.id, role);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao alterar o papel.");
    }
  }

  if (me?.role !== "admin") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        Você não tem permissão para ver a equipe.
      </div>
    );
  }

  return (
    <div className="mx-auto h-full max-w-3xl space-y-6 overflow-y-auto px-4 py-6">
      <FormError message={error} />

      <section className="rounded-lg border border-zinc-800 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-zinc-200">Convites</h2>
            <p className="text-xs text-zinc-500">
              Link de uso único (expira em 48h). Envie para cada novo membro da equipe.
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
          <div className="mt-3 flex items-center gap-2">
            <p className="flex-1 break-all rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs text-emerald-300">
              {inviteLink}
            </p>
            <button
              type="button"
              onClick={() => navigator.clipboard?.writeText(inviteLink)}
              className="shrink-0 rounded-md bg-zinc-800 px-2.5 py-2 text-xs text-zinc-200 hover:bg-zinc-700"
            >
              copiar
            </button>
          </div>
        )}
        {invites.length > 0 && (
          <ul className="mt-3 space-y-1">
            {invites.map((invite) => {
              const state = inviteState(invite);
              return (
                <li
                  key={invite.id}
                  className="flex items-center justify-between rounded-md bg-zinc-900 px-3 py-1.5 text-xs"
                >
                  <span className="font-mono text-zinc-400">
                    expira {new Date(invite.expires_at).toLocaleString("pt-BR")}
                  </span>
                  <span className={`rounded px-1.5 py-0.5 font-medium ${state.cls}`}>
                    {state.label}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Membros da equipe</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <th className="pb-2 font-medium">Nome</th>
              <th className="pb-2 font-medium">E-mail</th>
              <th className="pb-2 font-medium">Papel</th>
              <th className="pb-2 text-right font-medium">Ação</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id} className="border-t border-zinc-800/70">
                <td className="py-2 text-zinc-200">
                  {user.name}
                  {user.id === me.id && <span className="ml-1 text-xs text-zinc-500">(você)</span>}
                </td>
                <td className="py-2 text-zinc-400">{user.email}</td>
                <td className="py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                      user.role === "admin"
                        ? "bg-emerald-900/60 text-emerald-300"
                        : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {user.role}
                  </span>
                </td>
                <td className="py-2 text-right">
                  {user.role === "member" ? (
                    <button
                      type="button"
                      onClick={() => changeRole(user, "admin")}
                      className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-emerald-300 hover:bg-zinc-700"
                    >
                      Tornar admin
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => changeRole(user, "member")}
                      className="rounded-md bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-700"
                    >
                      Rebaixar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-zinc-500">
          Não é possível rebaixar o último administrador.
        </p>
      </section>
    </div>
  );
}
