import { afterEach, describe, expect, it, vi } from "vitest";
import { connectObserver, type ObserverHandlers } from "./observer";

/** Minimal WebSocket double: captures the instance so a test can drive
 * onopen/onmessage/onclose and inspect what was sent. */
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.onclose?.();
  }
}

function setup() {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
  const handlers: { [K in keyof ObserverHandlers]-?: ReturnType<typeof vi.fn> } = {
    onMessage: vi.fn(),
    onPresence: vi.fn(),
    onOnlineList: vi.fn(),
    onStatus: vi.fn(),
    onDelivered: vi.fn(),
    onActivity: vi.fn(),
    onKillSwitch: vi.fn(),
    onNotification: vi.fn(),
    onNotificationRead: vi.fn(),
    onKanbanDelta: vi.fn(),
    onReconnect: vi.fn(),
  };
  const stop = connectObserver(handlers as unknown as ObserverHandlers);
  const ws = MockWebSocket.instances.at(-1) as MockWebSocket;
  const recv = (frame: unknown) => ws.onmessage?.({ data: JSON.stringify(frame) });
  return { handlers, ws, recv, stop };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("connectObserver frame routing (panel WS contract)", () => {
  it("says hello on open and dispatches hello_ack (online + kill switch)", () => {
    const { handlers, ws } = setup();
    ws.onopen?.();
    expect(ws.sent[0]).toContain("hello");
    ws.onmessage?.({
      data: JSON.stringify({
        type: "hello_ack",
        online: ["a", "b"],
        auto_responder_enabled: false,
      }),
    });
    expect(handlers.onStatus).toHaveBeenCalledWith(true);
    expect(handlers.onOnlineList).toHaveBeenCalledWith(["a", "b"]);
    expect(handlers.onKillSwitch).toHaveBeenCalledWith(false);
  });

  it("routes every frame type to the matching handler", () => {
    const { handlers, recv } = setup();
    recv({ type: "message", message: { id: 1, body: "oi" } });
    expect(handlers.onMessage).toHaveBeenCalledWith({ id: 1, body: "oi" });

    recv({ type: "delivered", message_id: 7 });
    expect(handlers.onDelivered).toHaveBeenCalledWith(7);

    recv({ type: "presence", agent_id: "x", status: "online" });
    expect(handlers.onPresence).toHaveBeenCalledWith("x", true);

    recv({ type: "kill_switch", auto_responder_enabled: true });
    expect(handlers.onKillSwitch).toHaveBeenCalledWith(true);

    recv({ type: "notification", notification: { id: 3 } });
    expect(handlers.onNotification).toHaveBeenCalledWith({ id: 3 });

    recv({ type: "notification_read", ids: "all", unread_count: 0 });
    expect(handlers.onNotificationRead).toHaveBeenCalledWith("all", 0);

    recv({ type: "agent_activity", agent_id: "y", state: "responding" });
    expect(handlers.onActivity).toHaveBeenCalledWith("y", true);

    recv({ type: "kanban_delta", board_id: 1, op: "comment_added", comment: { id: 9 } });
    expect(handlers.onKanbanDelta).toHaveBeenCalledWith(
      expect.objectContaining({ type: "kanban_delta", op: "comment_added" }),
    );
  });

  it("ignores malformed frames and marks disconnected on close", () => {
    const { handlers, ws } = setup();
    expect(() => ws.onmessage?.({ data: "not json" })).not.toThrow();
    expect(handlers.onMessage).not.toHaveBeenCalled();
    ws.onclose?.();
    expect(handlers.onStatus).toHaveBeenCalledWith(false);
  });

  it("stops cleanly (closes the socket, no reconnect)", () => {
    const { ws, stop } = setup();
    stop();
    expect(ws.closed).toBe(true);
  });

  it("reconnects with exponential backoff, not a fixed delay", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0); // jitter floor → delay = exp/2
    const { ws } = setup();
    expect(MockWebSocket.instances).toHaveLength(1);

    ws.onclose?.(); // 1st drop: exp=1000 → 500ms
    vi.advanceTimersByTime(499);
    expect(MockWebSocket.instances).toHaveLength(1); // not yet
    vi.advanceTimersByTime(1);
    expect(MockWebSocket.instances).toHaveLength(2);

    MockWebSocket.instances.at(-1)?.onclose?.(); // 2nd drop backs off further: exp=2000 → 1000ms
    vi.advanceTimersByTime(999);
    expect(MockWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it("fires onReconnect after recovering from a drop, never on the first connect", () => {
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);
    const { handlers } = setup();
    const first = MockWebSocket.instances.at(-1) as MockWebSocket;
    first.onmessage?.({ data: JSON.stringify({ type: "hello_ack", online: [] }) });
    expect(handlers.onReconnect).not.toHaveBeenCalled(); // first connect is not a reconnect

    first.onclose?.();
    vi.advanceTimersByTime(500); // backoff fires → a fresh socket opens
    const second = MockWebSocket.instances.at(-1) as MockWebSocket;
    expect(second).not.toBe(first);
    second.onmessage?.({ data: JSON.stringify({ type: "hello_ack", online: [] }) });
    expect(handlers.onReconnect).toHaveBeenCalledTimes(1);
  });
});
