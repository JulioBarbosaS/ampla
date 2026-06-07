import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AgentsPage } from "./features/agents/AgentsPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { SetupPage } from "./features/auth/SetupPage";
import { ChatPage } from "./features/chat/ChatPage";
import { GroupsPage } from "./features/groups/GroupsPage";
import { authApi } from "./lib/api/auth";
import { useAuthStore } from "./stores/auth";

export default function App() {
  const token = useAuthStore((s) => s.token);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);

  useEffect(() => {
    authApi
      .setupStatus()
      .then(({ needs_setup }) => setNeedsSetup(needs_setup))
      .catch(() => setNeedsSetup(false)); // hub fora do ar → login mostra o erro
  }, []);

  if (needsSetup === null) {
    return (
      <div className="flex h-screen items-center justify-center text-zinc-400">
        Conectando ao hub…
      </div>
    );
  }

  if (needsSetup && !token) {
    return (
      <Routes>
        <Route path="*" element={<SetupPage onDone={() => setNeedsSetup(false)} />} />
      </Routes>
    );
  }

  if (!token) {
    return (
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
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
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
