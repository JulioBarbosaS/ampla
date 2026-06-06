import { beforeEach, describe, expect, it } from "vitest";
import type { Message } from "../lib/api/types";
import { conversationKey, useChatStore } from "./chat";

function msg(id: number, from: string, to: string, body = `m${id}`): Message {
  return { id, from, to, body, created_at: "2026-06-06T12:00:00Z", delivered_at: null };
}

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
  it("é simétrica (independe da direção)", () => {
    expect(conversationKey("a-x", "b-y")).toBe(conversationKey("b-y", "a-x"));
  });
});

describe("chat store", () => {
  it("addMessage agrupa pela conversa e deduplica por id", () => {
    const { addMessage } = useChatStore.getState();
    addMessage(msg(1, "backend-julio", "mobile-eduardo"));
    addMessage(msg(2, "mobile-eduardo", "backend-julio"));
    addMessage(msg(1, "backend-julio", "mobile-eduardo")); // eco do observer

    const key = conversationKey("backend-julio", "mobile-eduardo");
    const conversation = useChatStore.getState().conversations[key]!;
    expect(conversation.map((m) => m.id)).toEqual([1, 2]);
  });

  it("setConversation ordena cronologicamente (REST chega invertido)", () => {
    useChatStore
      .getState()
      .setConversation("a-x", "b-y", [msg(3, "a-x", "b-y"), msg(2, "b-y", "a-x"), msg(1, "a-x", "b-y")]);
    const conversation =
      useChatStore.getState().conversations[conversationKey("a-x", "b-y")]!;
    expect(conversation.map((m) => m.id)).toEqual([1, 2, 3]);
  });

  it("presença: setOnlineList zera e aplica; setPresence atualiza um", () => {
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

  it("trocar perspectiva limpa o parceiro selecionado", () => {
    const store = useChatStore.getState();
    store.setPartner("mobile-eduardo");
    store.setPerspective("infra-julio");
    expect(useChatStore.getState().partner).toBeNull();
  });
});
