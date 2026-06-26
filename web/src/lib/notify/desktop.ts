/**
 * Desktop notifications (Web Notifications API) — a delivery channel layered on
 * top of the in-app inbox. The hub already decides WHETHER an inbox item exists
 * (notify_level gating); this only mirrors arrivals to the OS when:
 *   - the user opted in (a panel toggle, persisted locally), AND
 *   - the browser granted permission, AND
 *   - the tab is not focused (otherwise the in-app inbox already shows it).
 *
 * Everything degrades gracefully where Notification is absent (SSR/jsdom).
 */

const STORAGE_KEY = "amp:desktop-notify";

export type DesktopPermission = NotificationPermission | "unsupported";

function supported(): boolean {
  return typeof window !== "undefined" && typeof Notification !== "undefined";
}

export function desktopPermission(): DesktopPermission {
  return supported() ? Notification.permission : "unsupported";
}

/** The toggle is "on" only if the user enabled it AND permission still holds. */
export function desktopNotifyEnabled(): boolean {
  return (
    supported() &&
    Notification.permission === "granted" &&
    localStorage.getItem(STORAGE_KEY) === "on"
  );
}

export function setDesktopNotifyEnabled(on: boolean): void {
  localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
}

/** Ask the browser for permission and turn the toggle on iff it was granted.
 * Returns the resulting permission so the UI can explain a denial. */
export async function requestDesktopPermission(): Promise<DesktopPermission> {
  if (!supported()) return "unsupported";
  const perm = await Notification.requestPermission();
  setDesktopNotifyEnabled(perm === "granted");
  return perm;
}

/** Mirror an inbox arrival to the OS, subject to the gates above. Clicking the
 * notification focuses the tab and deep-links to the item. `tag` collapses
 * repeats for the same subject so a chatty thread doesn't stack toasts. */
export function showDesktopNotification(
  n: { title: string; link: string; subject_key?: string },
  navigate?: (to: string) => void,
): void {
  if (!desktopNotifyEnabled()) return;
  // Don't double up with the inbox the user is already looking at.
  if (typeof document !== "undefined" && document.visibilityState === "visible") return;
  const notif = new Notification("Ampla", { body: n.title, tag: n.subject_key ?? n.link });
  notif.onclick = () => {
    window.focus();
    navigate?.(n.link);
    notif.close();
  };
}
