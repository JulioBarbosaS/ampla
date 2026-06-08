import { create } from "zustand";
import type { User } from "../lib/api/types";

/**
 * Who is logged in. The session itself lives in an HttpOnly cookie the browser
 * sends automatically — the JWT is never held in JavaScript (XSS can't read it).
 * So there is nothing to persist here: on boot App.tsx calls /api/auth/me to
 * learn whether the cookie is still valid, and `user` is the in-memory result.
 */
interface AuthState {
  user: User | null;
  setUser: (user: User) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  clear: () => set({ user: null }),
}));
