import { authApi } from "../../lib/api/auth";
import { useAuthStore } from "../../stores/auth";

const fieldClass =
  "w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300 disabled:cursor-not-allowed";

/** Account settings (reached from the topbar avatar). Profile editing is a
 * read-only placeholder for now — the backend endpoints to update name/email
 * and change the password don't exist yet (tracked to land later). Logout
 * lives here, in the red zone. */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);

  // Ask the hub to expire the cookie, then drop the in-memory user either way.
  // App.tsx renders the login screen once `user` is null.
  async function handleLogout() {
    await authApi.logout().catch(() => {});
    clear();
  }

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="mb-4 text-lg font-semibold text-zinc-100">Configurações</h1>

      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Perfil</h2>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Nome</span>
            <input value={user?.name ?? ""} disabled className={fieldClass} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-zinc-500">Email</span>
            <input value={user?.email ?? ""} disabled className={fieldClass} />
          </label>
          <div>
            <span className="mb-1 block text-xs text-zinc-500">Papel</span>
            <span className="inline-block rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300">
              {user?.role}
            </span>
          </div>
        </div>
        <p className="mt-3 text-xs text-zinc-600">A edição de perfil chega em breve.</p>
      </section>

      <section className="mt-4 rounded-lg border border-red-900/50 p-4">
        <h2 className="mb-1 text-sm font-medium text-red-300">Sair</h2>
        <p className="mb-3 text-xs text-zinc-500">Encerra sua sessão neste navegador.</p>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-500"
        >
          Sair da conta
        </button>
      </section>
    </div>
  );
}
