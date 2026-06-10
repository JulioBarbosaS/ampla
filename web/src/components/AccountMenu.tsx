import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../lib/api/auth";
import { useAuthStore } from "../stores/auth";
import { type Theme, useThemeStore } from "../stores/theme";

const THEMES: { value: Theme; label: string }[] = [
  { value: "dark", label: "Escuro" },
  { value: "light", label: "Claro" },
];

/**
 * The account drawer: opened from the topbar avatar, it drops down with the
 * account options — profile, theme, language (planned), and logout. It owns its
 * own open state and closes on outside-click / Escape.
 */
export function AccountMenu() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Ask the hub to expire the cookie, then drop the in-memory user either way.
  async function handleLogout() {
    setOpen(false);
    await authApi.logout().catch(() => {});
    clear();
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Conta e configurações"
        aria-haspopup="menu"
        aria-expanded={open}
        title={user?.name}
        onClick={() => setOpen((v) => !v)}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-800 text-sm font-semibold text-amber-300 transition-colors hover:bg-zinc-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
      >
        {user?.name?.charAt(0).toUpperCase() ?? "?"}
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Conta"
          className="absolute right-0 top-full z-30 mt-2 w-64 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900 shadow-lg shadow-black/40"
        >
          <div className="border-b border-zinc-800 px-3 py-3">
            <p className="truncate text-sm font-medium text-zinc-100">{user?.name}</p>
            <p className="truncate text-xs text-zinc-500">{user?.email}</p>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate("/settings");
            }}
            className="w-full px-3 py-2.5 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Perfil
          </button>

          {/* Theme: persisted selector. Only dark renders for real today; light
           * is wired and ready for the upcoming theme-token UI pass. */}
          <div className="px-3 py-2.5">
            <p className="mb-1.5 text-xs text-zinc-500">Tema</p>
            <div className="flex gap-1 rounded-md bg-zinc-800 p-1">
              {THEMES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={theme === option.value}
                  onClick={() => setTheme(option.value)}
                  className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                    theme === option.value
                      ? "bg-amber-500 text-zinc-950"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {/* Language: planned, not built yet. */}
          <div className="flex items-center justify-between px-3 py-2.5 text-sm text-zinc-600">
            <span>Idioma</span>
            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
              em breve
            </span>
          </div>

          <button
            type="button"
            role="menuitem"
            onClick={handleLogout}
            className="w-full border-t border-zinc-800 px-3 py-2.5 text-left text-sm font-medium text-red-400 transition-colors hover:bg-red-950/40"
          >
            Sair
          </button>
        </div>
      )}
    </div>
  );
}
