import { afterEach, describe, expect, it } from "vitest";
import { useThemeStore } from "./theme";

describe("theme store", () => {
  afterEach(() => {
    useThemeStore.getState().setTheme("dark");
    localStorage.clear();
  });

  it("applies and persists an explicit theme", () => {
    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().preference).toBe("light");
    expect(useThemeStore.getState().resolved).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("ampla-theme")).toBe("light");

    useThemeStore.getState().setTheme("dark");
    expect(useThemeStore.getState().resolved).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("ampla-theme")).toBe("dark");
  });

  it("resolves the system preference from the OS (matchMedia)", () => {
    useThemeStore.getState().setTheme("system");
    expect(useThemeStore.getState().preference).toBe("system");
    // matchMedia stub reports light → resolved is "light"
    expect(useThemeStore.getState().resolved).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("ampla-theme")).toBe("system");
  });
});
