import { useEffect } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { notificationsApi } from "../lib/api/notifications";
import { useAuthStore } from "../stores/auth";
import { useInboxStore } from "../stores/inbox";
import { useKillSwitchStore } from "../stores/killSwitch";
import { AccountMenu } from "./AccountMenu";
import { Logo } from "./Logo";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:text-zinc-50"
  }`;

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const autoResponderEnabled = useKillSwitchStore((s) => s.autoResponderEnabled);
  const unreadCount = useInboxStore((s) => s.unreadCount);
  const setUnreadCount = useInboxStore((s) => s.setUnreadCount);

  // Seed the badge on mount. While the panel is open it stays fresh via the
  // shared inbox store (the InboxPage sets it on every load/triage); live deltas
  // for notifications arriving elsewhere come with the WS slice.
  useEffect(() => {
    notificationsApi
      .unreadCount()
      .then((c) => setUnreadCount(c.unread_count))
      .catch(() => {});
  }, [setUnreadCount]);

  return (
    <div className="flex h-screen flex-col">
      {!autoResponderEnabled && (
        <div
          role="alert"
          className="bg-red-950/80 px-4 py-1.5 text-center text-xs font-medium text-red-200"
        >
          ⚠ Respostas automáticas suspensas pelo administrador (kill switch global). As mensagens
          continuam chegando à inbox.
        </div>
      )}
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

        <div className="flex items-center gap-3">
          <NavLink
            to="/inbox"
            aria-label={`Inbox${unreadCount > 0 ? ` (${unreadCount} não lidas)` : ""}`}
            className={({ isActive }) =>
              `relative rounded-md p-1.5 transition-colors ${
                isActive ? "text-zinc-50" : "text-zinc-400 hover:text-zinc-50"
              }`
            }
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
              <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
            </svg>
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-500 px-1 text-[10px] font-semibold text-zinc-950">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </NavLink>
          <AccountMenu />
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
