import { afterEach, describe, expect, it } from "vitest";
import { useAvatarStore } from "./avatar";

const DATA_URL = "data:image/jpeg;base64,abc";

describe("avatar store", () => {
  afterEach(() => {
    useAvatarStore.setState({ photos: {} });
    localStorage.clear();
  });

  it("stores a photo per user and persists it", () => {
    useAvatarStore.getState().setPhoto(1, DATA_URL);
    expect(useAvatarStore.getState().photos[1]).toBe(DATA_URL);
    expect(JSON.parse(localStorage.getItem("ampla-avatars") ?? "{}")[1]).toBe(DATA_URL);
  });

  it("keeps photos isolated by user id", () => {
    useAvatarStore.getState().setPhoto(1, DATA_URL);
    useAvatarStore.getState().setPhoto(2, "data:image/jpeg;base64,xyz");
    expect(useAvatarStore.getState().photos[1]).toBe(DATA_URL);
    expect(useAvatarStore.getState().photos[2]).toBe("data:image/jpeg;base64,xyz");
  });

  it("removes a photo and drops it from storage", () => {
    useAvatarStore.getState().setPhoto(1, DATA_URL);
    useAvatarStore.getState().removePhoto(1);
    expect(useAvatarStore.getState().photos[1]).toBeUndefined();
    expect(JSON.parse(localStorage.getItem("ampla-avatars") ?? "{}")[1]).toBeUndefined();
  });
});
