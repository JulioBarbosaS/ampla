import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  desktopNotifyEnabled,
  desktopPermission,
  requestDesktopPermission,
  setDesktopNotifyEnabled,
  showDesktopNotification,
} from "./desktop";

/** Notification double: static permission + requestPermission, instances capture
 * onclick so a test can drive the click. */
class MockNotification {
  static permission: NotificationPermission = "granted";
  static requestPermission = vi.fn(async () => MockNotification.permission);
  static instances: MockNotification[] = [];
  onclick: (() => void) | null = null;
  close = vi.fn();
  constructor(
    public title: string,
    public options?: NotificationOptions,
  ) {
    MockNotification.instances.push(this);
  }
}

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

beforeEach(() => {
  localStorage.clear();
  MockNotification.permission = "granted";
  MockNotification.instances = [];
  MockNotification.requestPermission.mockClear();
  vi.stubGlobal("Notification", MockNotification);
  setVisibility("hidden");
});

afterEach(() => {
  // Restore ONLY Notification — unstubAllGlobals would also wipe the setup's
  // localStorage stub and break the next test's beforeEach.
  vi.stubGlobal("Notification", undefined);
  setVisibility("visible");
});

describe("desktop notifications", () => {
  it("reports unsupported when Notification is absent", () => {
    vi.stubGlobal("Notification", undefined);
    expect(desktopPermission()).toBe("unsupported");
    expect(desktopNotifyEnabled()).toBe(false);
  });

  it("requesting permission turns the opt-in on only when granted", async () => {
    expect(await requestDesktopPermission()).toBe("granted");
    expect(desktopNotifyEnabled()).toBe(true);

    MockNotification.permission = "denied";
    expect(await requestDesktopPermission()).toBe("denied");
    expect(desktopNotifyEnabled()).toBe(false);
  });

  it("is enabled only when granted AND opted in", () => {
    setDesktopNotifyEnabled(true);
    expect(desktopNotifyEnabled()).toBe(true);
    MockNotification.permission = "default"; // permission revoked → off, despite the opt-in
    expect(desktopNotifyEnabled()).toBe(false);
  });

  it("shows a notification only when enabled and the tab is hidden", () => {
    setDesktopNotifyEnabled(true);
    showDesktopNotification({ title: "nova msg", link: "/x", subject_key: "dm:a:b" });
    expect(MockNotification.instances).toHaveLength(1);
    expect(MockNotification.instances[0].options?.body).toBe("nova msg");
    expect(MockNotification.instances[0].options?.tag).toBe("dm:a:b"); // collapses repeats
  });

  it("stays silent when the tab is focused (the inbox already shows it)", () => {
    setDesktopNotifyEnabled(true);
    setVisibility("visible");
    showDesktopNotification({ title: "x", link: "/x" });
    expect(MockNotification.instances).toHaveLength(0);
  });

  it("stays silent when not opted in", () => {
    showDesktopNotification({ title: "x", link: "/x" });
    expect(MockNotification.instances).toHaveLength(0);
  });

  it("click focuses the window and deep-links to the item", () => {
    setDesktopNotifyEnabled(true);
    const focus = vi.spyOn(window, "focus").mockImplementation(() => {});
    const navigate = vi.fn();
    showDesktopNotification({ title: "x", link: "/go" }, navigate);
    MockNotification.instances[0].onclick?.();
    expect(focus).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/go");
  });
});
