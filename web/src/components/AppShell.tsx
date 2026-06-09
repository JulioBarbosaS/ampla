import { NavLink, Outlet } from "react-router-dom";
import { authApi } from "../lib/api/auth";
import { useAuthStore } from "../stores/auth";
import { Logo } from "./Logo";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
  }`;

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);

  // Ask the hub to expire the cookie, then drop the in-memory user either way.
  async function handleLogout() {
    await authApi.logout().catch(() => {});
    clear();
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <div className="flex items-center gap-4">
          <Logo variant="icon" className="h-6 w-6" />
          <nav className="flex gap-1">
            <NavLink to="/" className={linkClass} end>
              Conversas
            </NavLink>
            <NavLink to="/groups" className={linkClass}>
              Grupos
            </NavLink>
            <NavLink to="/agents" className={linkClass}>
              Meus agentes
            </NavLink>
            {user?.role === "admin" && (
              <NavLink to="/team" className={linkClass}>
                Equipe
              </NavLink>
            )}
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
            onClick={handleLogout}
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
