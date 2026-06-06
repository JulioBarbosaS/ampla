import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom não implementa scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

afterEach(() => {
  cleanup();
});
