import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AgentsPage } from "./features/agents/AgentsPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { ResetPasswordPage } from "./features/auth/ResetPasswordPage";
import { SetupPage } from "./features/auth/SetupPage";
import { ChatPage } from "./features/chat/ChatPage";
import { GroupsPage } from "./features/groups/GroupsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { TeamPage } from "./features/team/TeamPage";
import { authApi } from "./lib/api/auth";
import { useAuthStore } from "./stores/auth";

export default function App() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);

  // Boot: ask whether setup is pending and whether the session cookie is still
  // valid (/me). The JWT lives only in the HttpOnly cookie, so the server is
  // the source of truth — there is nothing to rehydrate from storage.
  useEffect(() => {
    Promise.all([
      authApi
        .setupStatus()
        .then(({ needs_setup }) => needs_setup)
        .catch(() => false), // hub down → login screen shows the error
      authApi
        .me()
        .then(setUser)
        .catch(() => {}), // 401 → not logged in, stays on login
    ]).then(([needs]) => setNeedsSetup(needs));
  }, [setUser]);

  if (needsSetup === null) {
    return (
      <div className="flex h-screen items-center justify-center text-zinc-400">
        Conectando ao hub…
      </div>
    );
  }

  if (needsSetup && !user) {
    return (
      <Routes>
        <Route path="*" element={<SetupPage onDone={() => setNeedsSetup(false)} />} />
      </Routes>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/reset" element={<ResetPasswordPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<ChatPage />} />
        <Route path="/groups" element={<GroupsPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
