import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../lib/api/auth";
import { useAuthStore } from "../stores/auth";
import { type ThemePreference, useThemeStore } from "../stores/theme";

const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Claro" },
  { value: "dark", label: "Escuro" },
  { value: "system", label: "Tema do dispositivo" },
];

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function Check() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

/**
 * The account drawer: opened from the topbar avatar, it drops down with the
 * account options — profile, theme, language (planned), and logout. It owns its
 * own open state and closes on outside-click / Escape.
 */
export function AccountMenu() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const preference = useThemeStore((s) => s.preference);
  const setTheme = useThemeStore((s) => s.setTheme);
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
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

  // Collapse the theme sub-list whenever the whole drawer closes.
  useEffect(() => {
    if (!open) setThemeOpen(false);
  }, [open]);

  // Ask the hub to expire the cookie, then drop the in-memory user either way.
  async function handleLogout() {
    setOpen(false);
    await authApi.logout().catch(() => {});
    clear();
  }

  const currentTheme = THEME_OPTIONS.find((option) => option.value === preference)?.label ?? "";

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
          <div className="flex items-center gap-3 border-b border-zinc-800 px-3 py-3">
            {/* No photo field yet (upload is a future feature) — the initial
             * stands in for the avatar, like the topbar trigger. */}
            <span
              aria-hidden="true"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm font-semibold text-amber-300"
            >
              {user?.name?.charAt(0).toUpperCase() ?? "?"}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-100">{user?.name}</p>
              <p className="truncate text-xs text-zinc-500">{user?.email}</p>
            </div>
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

          {/* Theme: shows the current choice; clicking expands the options
           * (light / dark / follow the device). */}
          <button
            type="button"
            aria-label="Tema"
            aria-expanded={themeOpen}
            onClick={() => setThemeOpen((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            <span>Tema</span>
            <span className="flex items-center gap-1.5 text-xs text-zinc-500">
              {currentTheme}
              <Chevron open={themeOpen} />
            </span>
          </button>
          {themeOpen && (
            <ul className="bg-zinc-950/40 py-1">
              {THEME_OPTIONS.map((option) => (
                <li key={option.value}>
                  <button
                    type="button"
                    aria-pressed={preference === option.value}
                    onClick={() => setTheme(option.value)}
                    className={`flex w-full items-center justify-between py-2 pr-3 pl-6 text-left text-sm transition-colors hover:bg-zinc-800 ${
                      preference === option.value ? "text-amber-300" : "text-zinc-400"
                    }`}
                  >
                    <span>{option.label}</span>
                    {preference === option.value && <Check />}
                  </button>
                </li>
              ))}
            </ul>
          )}

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
