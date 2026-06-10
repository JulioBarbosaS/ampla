import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom does not implement scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

// Node 25 ships a native `localStorage` global that, without --localstorage-file,
// shadows jsdom's with a non-functional stub. Replace it with a real in-memory
// Storage so persistence behaves like a browser.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.get(key) ?? null;
  }
  key(index: number) {
    return [...this.store.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}
vi.stubGlobal("localStorage", new MemoryStorage());

afterEach(() => {
  cleanup();
});
