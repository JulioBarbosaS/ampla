import { useAuthStore } from "../../stores/auth";

const fieldClass =
  "w-full rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300 disabled:cursor-not-allowed";

/** Profile page (reached from the account drawer → "Perfil"). Editing is a
 * read-only placeholder for now — the backend endpoints to update name/email
 * and change the password don't exist yet (tracked to land later). Theme,
 * language and logout live in the account drawer. */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="mb-4 text-lg font-semibold text-zinc-100">Perfil</h1>

      <section className="rounded-lg border border-zinc-800 p-4">
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
    </div>
  );
}
