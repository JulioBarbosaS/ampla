import { afterEach, describe, expect, it } from "vitest";
import { useAvatarStore } from "./avatar";

describe("avatar store", () => {
  afterEach(() => useAvatarStore.setState({ version: {}, present: {} }));

  it("bumps the per-user cache-busting version", () => {
    useAvatarStore.getState().bump(1);
    expect(useAvatarStore.getState().version[1]).toBe(1);
    useAvatarStore.getState().bump(1);
    expect(useAvatarStore.getState().version[1]).toBe(2);
  });

  it("tracks presence per user", () => {
    useAvatarStore.getState().setPresent(1, true);
    expect(useAvatarStore.getState().present[1]).toBe(true);
    useAvatarStore.getState().setPresent(1, false);
    expect(useAvatarStore.getState().present[1]).toBe(false);
  });
});
