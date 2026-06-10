import { NavLink, Outlet } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import { AccountMenu } from "./AccountMenu";
import { Logo } from "./Logo";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
  }`;

export function AppShell() {
  const user = useAuthStore((s) => s.user);

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

        <AccountMenu />
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
