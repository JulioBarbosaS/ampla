import { beforeEach, describe, expect, it } from "vitest";
import type { AppNotification } from "../lib/api/types";
import { useInboxStore } from "./inbox";

function notif(id: number, over: Partial<AppNotification> = {}): AppNotification {
  return {
    id,
    subject_type: "dm",
    subject_key: `dm:a:b-${id}`,
    agent_slug: "backend-julio",
    reason: "direct_message",
    title: `t${id}`,
    link: "",
    actor: "mobile-eduardo",
    unread: true,
    status: "inbox",
    created_at: "",
    updated_at: "",
    last_read_at: null,
    ...over,
  };
}

beforeEach(() => useInboxStore.setState({ items: [], unreadCount: 0 }));

describe("inbox store", () => {
  it("clamps the unread count at zero", () => {
    useInboxStore.getState().setUnreadCount(-3);
    expect(useInboxStore.getState().unreadCount).toBe(0);
    useInboxStore.getState().setUnreadCount(5);
    expect(useInboxStore.getState().unreadCount).toBe(5);
  });

  it("patch replaces a row in place, keeping order", () => {
    useInboxStore.getState().setItems([notif(1), notif(2)]);
    useInboxStore.getState().patch(notif(2, { unread: false, title: "lido" }));
    const items = useInboxStore.getState().items;
    expect(items.map((n) => n.id)).toEqual([1, 2]);
    expect(items[1]?.title).toBe("lido");
    expect(items[1]?.unread).toBe(false);
  });
});
