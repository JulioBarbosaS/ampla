import { afterEach, describe, expect, it } from "vitest";
import { useThemeStore } from "./theme";

describe("theme store", () => {
  afterEach(() => {
    useThemeStore.getState().setTheme("dark");
    localStorage.clear();
  });

  it("reflects the theme on <html> and persists the choice", () => {
    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().theme).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("ampla-theme")).toBe("light");

    useThemeStore.getState().setTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("ampla-theme")).toBe("dark");
  });
});
