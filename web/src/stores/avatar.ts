import { create } from "zustand";

/**
 * Profile photos, kept client-side for now (no upload endpoint yet). Each photo
 * is a cropped data URL stored per user id in localStorage, so it survives a
 * reload. When the backend lands, this becomes the cache in front of it.
 */
const STORAGE_KEY = "ampla-avatars";

function readStored(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

function persist(photos: Record<string, string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(photos));
  } catch {
    // storage full/disabled — keep the in-memory copy anyway
  }
}

interface AvatarState {
  photos: Record<string, string>;
  setPhoto: (userId: number, dataUrl: string) => void;
  removePhoto: (userId: number) => void;
}

export const useAvatarStore = create<AvatarState>()((set, get) => ({
  photos: readStored(),
  setPhoto: (userId, dataUrl) => {
    const photos = { ...get().photos, [userId]: dataUrl };
    persist(photos);
    set({ photos });
  },
  removePhoto: (userId) => {
    const photos = { ...get().photos };
    delete photos[userId];
    persist(photos);
    set({ photos });
  },
}));
