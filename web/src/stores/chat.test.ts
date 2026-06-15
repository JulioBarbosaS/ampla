import { beforeEach, describe, expect, it } from "vitest";
import type { Message } from "../lib/api/types";
import { conversationKey, groupThreads, useChatStore } from "./chat";

function msg(id: number, from: string, to: string, body = `m${id}`): Message {
  return {
    id,
    from,
    to,
    body,
    type: "request" as const,
    priority: "normal" as const,
    group: null,
    thread_id: id,
    in_reply_to: null,
    created_at: "2026-06-06T12:00:00Z",
    delivered_at: null,
    expires_at: null,
  };
}

describe("groupThreads", () => {
  it("groups replies under the root identified by id === thread_id", () => {
    const root = { ...msg(1, "a", "b"), thread_id: 1 };
    const reply = { ...msg(3, "b", "a"), thread_id: 1, in_reply_to: 1 };
    const other = { ...msg(2, "a", "b"), thread_id: 2 };
    const threads = groupThreads([reply, other, root]);
    expect(threads).toHaveLength(2);
    // ordered by root id
    expect(threads[0].root.id).toBe(1);
    expect(threads[0].replies.map((m) => m.id)).toEqual([3]);
    expect(threads[1].root.id).toBe(2);
    expect(threads[1].replies).toHaveLength(0);
  });

  it("treats a message with no matching root as its own thread", () => {
    const orphan = { ...msg(5, "a", "b"), thread_id: 99, in_reply_to: 99 };
    const threads = groupThreads([orphan]);
    expect(threads).toHaveLength(1);
    expect(threads[0].root.id).toBe(5);
  });
});

beforeEach(() => {
  useChatStore.setState({
    perspective: null,
    partner: null,
    directory: [],
    online: {},
    conversations: {},
  });
});

describe("conversationKey", () => {
  it("is symmetric (direction-independent)", () => {
    expect(conversationKey("a-x", "b-y")).toBe(conversationKey("b-y", "a-x"));
  });
});

describe("chat store", () => {
  it("addMessage groups by conversation and dedupes by id", () => {
    const { addMessage } = useChatStore.getState();
    addMessage(msg(1, "backend-julio", "mobile-eduardo"));
    addMessage(msg(2, "mobile-eduardo", "backend-julio"));
    addMessage(msg(1, "backend-julio", "mobile-eduardo")); // observer echo

    const key = conversationKey("backend-julio", "mobile-eduardo");
    const conversation = useChatStore.getState().conversations[key]!;
    expect(conversation.map((m) => m.id)).toEqual([1, 2]);
  });

  it("setConversation sorts chronologically (REST arrives reversed)", () => {
    useChatStore
      .getState()
      .setConversation("a-x", "b-y", [
        msg(3, "a-x", "b-y"),
        msg(2, "b-y", "a-x"),
        msg(1, "a-x", "b-y"),
      ]);
    const conversation = useChatStore.getState().conversations[conversationKey("a-x", "b-y")]!;
    expect(conversation.map((m) => m.id)).toEqual([1, 2, 3]);
  });

  it("presence: setOnlineList resets and applies; setPresence updates one", () => {
    const store = useChatStore.getState();
    store.setDirectory([
      { slug: "backend-julio", display_name: "B", online: true },
      { slug: "mobile-eduardo", display_name: "M", online: false },
    ]);
    store.setOnlineList(["mobile-eduardo"]);
    expect(useChatStore.getState().online).toMatchObject({
      "backend-julio": false,
      "mobile-eduardo": true,
    });

    store.setPresence("backend-julio", true);
    expect(useChatStore.getState().online["backend-julio"]).toBe(true);
  });

  it("switching perspective clears the selected partner", () => {
    const store = useChatStore.getState();
    store.setPartner("mobile-eduardo");
    store.setPerspective("infra-julio");
    expect(useChatStore.getState().partner).toBeNull();
  });

  it("markDelivered stamps the bubble's delivery when the ack (delivered) arrives", () => {
    const store = useChatStore.getState();
    store.addMessage(msg(1, "backend-julio", "mobile-eduardo")); // delivered_at: null
    store.markDelivered(1);
    const key = conversationKey("backend-julio", "mobile-eduardo");
    expect(useChatStore.getState().conversations[key]![0].delivered_at).not.toBeNull();
  });

  it("markDelivered ignores a nonexistent id without breaking", () => {
    const store = useChatStore.getState();
    store.addMessage(msg(1, "backend-julio", "mobile-eduardo"));
    expect(() => store.markDelivered(999)).not.toThrow();
  });

  it("addMessage syncs delivered_at from a re-mirror of a message we already have", () => {
    const store = useChatStore.getState();
    const key = conversationKey("backend-julio", "mobile-eduardo");
    store.addMessage(msg(1, "backend-julio", "mobile-eduardo")); // our POST: delivered_at null
    expect(useChatStore.getState().conversations[key]![0].delivered_at).toBeNull();

    // the hub re-mirrors the SAME message after the recipient acks (delivered set)
    store.addMessage({
      ...msg(1, "backend-julio", "mobile-eduardo"),
      delivered_at: "2026-06-15T12:00:00Z",
    });

    const conversation = useChatStore.getState().conversations[key]!;
    expect(conversation).toHaveLength(1); // still deduped (no duplicate bubble)
    expect(conversation[0].delivered_at).toBe("2026-06-15T12:00:00Z"); // but now "entregue"
  });
});
