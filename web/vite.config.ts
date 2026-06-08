/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Proxy /api and /ws to the hub so the browser only ever talks to the dev
// server's origin. Same origin is what lets the HttpOnly SameSite=Strict
// session cookie travel in dev (and is how prod works, hub-served). Point it
// at another hub with VITE_HUB_PROXY (the e2e run targets its throwaway hub).
const HUB = process.env.VITE_HUB_PROXY ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: HUB, changeOrigin: true },
      "/ws": { target: HUB, changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["src/main.tsx", "src/test/**", "src/vite-env.d.ts"],
      // gate baixo de propósito: fase backend-first; sobe na passada de UI/UX
      thresholds: {
        lines: 25,
        functions: 40,
        statements: 25,
        branches: 70,
      },
    },
  },
});
