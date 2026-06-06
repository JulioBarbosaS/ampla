import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { User } from "../lib/api/types";

/** localStorage funcional, com probe: Node ≥22 expõe um localStorage
 * experimental inerte que sombrearia o do jsdom nos testes. */
function safeStorage(): Storage {
  try {
    const storage = window.localStorage;
    storage.setItem("__amp_probe__", "1");
    storage.removeItem("__amp_probe__");
    return storage;
  } catch {
    const data = new Map<string, string>();
    return {
      getItem: (key) => data.get(key) ?? null,
      setItem: (key, value) => void data.set(key, value),
      removeItem: (key) => void data.delete(key),
      clear: () => data.clear(),
      key: (index) => [...data.keys()][index] ?? null,
      get length() {
        return data.size;
      },
    } as Storage;
  }
}

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    {
      name: "amp-auth",
      storage: createJSONStorage(safeStorage),
    }
  )
);
