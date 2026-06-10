import { useEffect } from "react";
import { agentsApi } from "../../lib/api/agents";
import { messagesApi } from "../../lib/api/messages";
import { connectObserver } from "../../lib/ws/observer";
import { useAuthStore } from "../../stores/auth";
import { useChatStore } from "../../stores/chat";
import { ChatWindow } from "./ChatWindow";
import { Sidebar } from "./Sidebar";

export function ChatPage() {
  const authed = useAuthStore((s) => s.user !== null);
  const { perspective, partner, wsConnected } = useChatStore();
  const {
    setDirectory,
    setOnlineList,
    setPresence,
    addMessage,
    setConversation,
    setPerspective,
    setWsConnected,
    markDelivered,
    setActivity,
  } = useChatStore();

  // directory + initial perspective (the user's first agent)
  useEffect(() => {
    agentsApi
      .directory()
      .then(setDirectory)
      .catch(() => {});
    agentsApi
      .mine()
      .then((mine) => {
        const current = useChatStore.getState().perspective;
        if (!current && mine[0]) setPerspective(mine[0].slug);
      })
      .catch(() => {});
  }, [setDirectory, setPerspective]);

  // real time (WS observer)
  useEffect(() => {
    if (!authed) return;
    return connectObserver({
      onMessage: addMessage,
      onPresence: setPresence,
      onOnlineList: setOnlineList,
      onStatus: setWsConnected,
      onDelivered: markDelivered,
      onActivity: setActivity,
    });
  }, [authed, addMessage, setPresence, setOnlineList, setWsConnected, markDelivered, setActivity]);

  // history of the selected conversation
  useEffect(() => {
    if (!perspective || !partner) return;
    messagesApi
      .conversation(perspective, partner)
      .then((messages) => setConversation(perspective, partner, messages))
      .catch(() => {});
  }, [perspective, partner, setConversation]);

  return (
    <div className="flex h-full flex-col">
      {!wsConnected && (
        <div role="status" className="bg-amber-900/40 px-4 py-1 text-center text-xs text-amber-300">
          reconectando ao hub…
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <ChatWindow />
      </div>
    </div>
  );
}
