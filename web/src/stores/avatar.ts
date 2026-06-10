import { create } from "zustand";

/**
 * Avatar view-state. Photos now live on the hub (served at
 * `/api/users/{id}/avatar`); this store no longer holds bytes — only a per-user
 * cache-busting `version` (bumped after upload/remove to force a reload) and a
 * `present` flag the <Avatar> sets from the image load result, so the UI can
 * show a "remove" affordance only when there is a photo.
 */
interface AvatarState {
  version: Record<number, number>;
  present: Record<number, boolean>;
  bump: (userId: number) => void;
  setPresent: (userId: number, present: boolean) => void;
}

export const useAvatarStore = create<AvatarState>()((set) => ({
  version: {},
  present: {},
  bump: (userId) =>
    set((s) => ({ version: { ...s.version, [userId]: (s.version[userId] ?? 0) + 1 } })),
  setPresent: (userId, present) =>
    set((s) =>
      s.present[userId] === present ? s : { present: { ...s.present, [userId]: present } },
    ),
}));
