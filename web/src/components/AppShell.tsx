import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { authApi } from "../lib/api/auth";
import { useAuthStore } from "../stores/auth";
import { Logo } from "./Logo";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-white"
  }`;

function GearIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

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

        <div ref={menuRef} className="relative flex items-center gap-2">
          {user?.role === "admin" && (
            <span className="rounded bg-amber-900/50 px-1.5 py-0.5 text-xs text-amber-300">
              admin
            </span>
          )}
          <span
            title={user?.name}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-sm font-semibold text-amber-300"
          >
            {user?.name?.charAt(0).toUpperCase() ?? "?"}
          </span>
          <button
            type="button"
            aria-label="configurações"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-white"
          >
            <GearIcon />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-30 mt-2 w-52 rounded-md border border-zinc-800 bg-zinc-900 py-1 shadow-lg shadow-black/40">
              <div className="border-b border-zinc-800 px-3 py-2">
                <p className="truncate text-sm text-zinc-200">{user?.name}</p>
                <p className="truncate text-xs text-zinc-500">{user?.email}</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/settings");
                }}
                className="w-full px-3 py-2 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
              >
                Configurações
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  handleLogout();
                }}
                className="w-full px-3 py-2 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
              >
                Sair
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
