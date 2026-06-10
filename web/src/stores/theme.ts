import { create } from "zustand";

/** What the user picked. "system" follows the OS via prefers-color-scheme. */
export type ThemePreference = "light" | "dark" | "system";
/** The theme actually applied to the document. */
type Resolved = "light" | "dark";

const STORAGE_KEY = "ampla-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function readStored(): ThemePreference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" || value === "system" ? value : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  // jsdom (and very old browsers) lack matchMedia — default to dark.
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia(DARK_QUERY).matches;
}

function resolve(preference: ThemePreference): Resolved {
  if (preference === "system") return systemPrefersDark() ? "dark" : "light";
  return preference;
}

/**
 * Reflect the resolved theme on <html> so CSS can target it. `index.css` keys
 * the light palette off `[data-theme="light"]` (it inverts the neutral scale);
 * the `dark` class is kept for any future `dark:` variants.
 */
function apply(resolved: Resolved): void {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.classList.toggle("dark", resolved === "dark");
}

interface ThemeState {
  preference: ThemePreference;
  resolved: Resolved;
  setTheme: (preference: ThemePreference) => void;
}

export const useThemeStore = create<ThemeState>()((set, get) => {
  // Follow the OS while the preference is "system": re-resolve when it flips.
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    window.matchMedia(DARK_QUERY).addEventListener?.("change", () => {
      if (get().preference !== "system") return;
      const resolved = systemPrefersDark() ? "dark" : "light";
      apply(resolved);
      set({ resolved });
    });
  }

  const preference = readStored();
  const resolved = resolve(preference);
  apply(resolved);

  return {
    preference,
    resolved,
    setTheme: (preference) => {
      const resolved = resolve(preference);
      apply(resolved);
      try {
        localStorage.setItem(STORAGE_KEY, preference);
      } catch {
        // storage disabled (private mode) — keep the in-memory choice anyway
      }
      set({ preference, resolved });
    },
  };
});
