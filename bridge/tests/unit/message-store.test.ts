import { appendFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MessageStore, type StoredMessage } from "../../src/daemon/message-store.js";

let dir: string;
let path: string;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "amp-store-"));
  path = join(dir, "messages.jsonl");
});

afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

function incoming(id: number, from = "mobile-eduardo", body = `msg ${id}`): StoredMessage {
  return {
    id,
    from,
    to: "backend-julio",
    body,
    ts: new Date(2026, 5, 6, 12, 0, id).toISOString(),
    direction: "in",
    read: false,
  };
}

describe("MessageStore", () => {
  it("persiste e recarrega do disco", () => {
    const store = new MessageStore(path);
    store.append(incoming(1));
    store.append(incoming(2));

    const reloaded = new MessageStore(path);
    expect(reloaded.inbox(false)).toHaveLength(2);
  });

  it("deduplica reentrega por id do hub", () => {
    const store = new MessageStore(path);
    store.append(incoming(1));
    store.append(incoming(1)); // reconexão reentrega pendentes
    expect(store.inbox(false)).toHaveLength(1);
  });

  it("inbox não lidas e markRead", () => {
    const store = new MessageStore(path);
    store.append(incoming(1));
    store.append(incoming(2));
    store.markRead([1]);
    expect(store.unreadCount()).toBe(1);
    expect(store.inbox(true).map((m) => m.id)).toEqual([2]);

    // estado de leitura sobrevive ao reload
    const reloaded = new MessageStore(path);
    expect(reloaded.unreadCount()).toBe(1);
  });

  it("conversation filtra por parceiro nas duas direções", () => {
    const store = new MessageStore(path);
    store.append(incoming(1, "mobile-eduardo"));
    store.append(incoming(2, "frontend-joao"));
    store.append({
      id: null,
      from: "backend-julio",
      to: "mobile-eduardo",
      body: "resposta",
      ts: new Date().toISOString(),
      direction: "out",
      read: true,
    });
    const conversation = store.conversation("mobile-eduardo");
    expect(conversation).toHaveLength(2);
    expect(conversation.at(-1)?.body).toBe("resposta");
  });

  it("partners lista os interlocutores", () => {
    const store = new MessageStore(path);
    store.append(incoming(1, "mobile-eduardo"));
    store.append(incoming(2, "frontend-joao"));
    expect(store.partners()).toEqual(["frontend-joao", "mobile-eduardo"]);
  });

  it("linha corrompida no JSONL é ignorada sem derrubar", () => {
    const store = new MessageStore(path);
    store.append(incoming(1));
    appendFileSync(path, "linha corrompida\n");
    const reloaded = new MessageStore(path);
    expect(reloaded.inbox(false)).toHaveLength(1);
  });
});
