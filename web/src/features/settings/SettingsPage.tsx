import { useAuthStore } from "../../stores/auth";

/** Account settings (reached from the topbar gear). Minimal for now — shows the
 * signed-in account; more options land here later. */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <div className="mx-auto max-w-lg p-6">
      <h1 className="mb-4 text-lg font-semibold text-zinc-100">Configurações</h1>
      <section className="rounded-lg border border-zinc-800 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-300">Conta</h2>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">Nome</dt>
            <dd className="truncate text-zinc-200">{user?.name}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">Email</dt>
            <dd className="truncate text-zinc-200">{user?.email}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-zinc-500">Papel</dt>
            <dd className="text-zinc-200">{user?.role}</dd>
          </div>
        </dl>
      </section>
      <p className="mt-4 text-xs text-zinc-600">Mais opções em breve.</p>
    </div>
  );
}
