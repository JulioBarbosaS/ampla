import { create } from "zustand";

export type Theme = "dark" | "light";

const STORAGE_KEY = "ampla-theme";

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

/**
 * Reflect the chosen theme on <html> so CSS can target it. Only the dark
 * palette is actually implemented today; "light" is persisted and applied here
 * so it starts rendering for real once the components move to theme tokens (the
 * deferred UI pass) — no further wiring needed then.
 */
function apply(theme: Theme): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "dark");
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

export const useThemeStore = create<ThemeState>()((set) => {
  const initial = readStored();
  apply(initial);
  return {
    theme: initial,
    setTheme: (theme) => {
      apply(theme);
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch {
        // storage disabled (private mode) — keep the in-memory choice anyway
      }
      set({ theme });
    },
  };
});
