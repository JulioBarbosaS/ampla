import { NavLink, Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
  }`;

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-4">
          <span className="text-sm font-bold tracking-wide text-emerald-400">Ampla</span>
          <nav className="flex gap-1">
            <NavLink to="/" className={linkClass} end>
              Conversas
            </NavLink>
            <NavLink to="/agents" className={linkClass}>
              Meus agentes
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm text-zinc-400">
          <span>
            {user?.name}
            {user?.role === "admin" && (
              <span className="ml-1.5 rounded bg-emerald-900/60 px-1.5 py-0.5 text-xs text-emerald-300">
                admin
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={logout}
            className="rounded-md px-2 py-1 text-zinc-500 hover:bg-zinc-800 hover:text-white"
          >
            Sair
          </button>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
