import { useCallback, useEffect } from "react";
import { agentsApi } from "../../lib/api/agents";
import { messagesApi } from "../../lib/api/messages";
import type { AppNotification } from "../../lib/api/types";
import { connectObserver } from "../../lib/ws/observer";
import { useAuthStore } from "../../stores/auth";
import { useChatStore } from "../../stores/chat";
import { useInboxStore } from "../../stores/inbox";
import { useKillSwitchStore } from "../../stores/killSwitch";
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
  const setAutoResponderEnabled = useKillSwitchStore((s) => s.setAutoResponderEnabled);

  // Inbox deltas (Epic 02 · slice b). Handlers read/write the store via getState
  // so they stay stable (no re-subscribe churn on the observer effect).
  const onNotification = useCallback((n: AppNotification) => {
    const s = useInboxStore.getState();
    const was = s.items.find((i) => i.id === n.id);
    s.upsert(n);
    // count it once when it (re)enters the unread set — not on an already-unread bump
    if (n.unread && !was?.unread) {
      s.setUnreadCount(useInboxStore.getState().unreadCount + 1);
    }
  }, []);
  const onNotificationRead = useCallback((ids: number[] | "all", unreadCount: number) => {
    const s = useInboxStore.getState();
    s.markRead(ids);
    s.setUnreadCount(unreadCount);
  }, []);

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
      onKillSwitch: setAutoResponderEnabled,
      onNotification,
      onNotificationRead,
    });
  }, [
    authed,
    addMessage,
    setPresence,
    setOnlineList,
    setWsConnected,
    markDelivered,
    setActivity,
    setAutoResponderEnabled,
    onNotification,
    onNotificationRead,
  ]);

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
