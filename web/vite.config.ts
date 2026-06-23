/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Config is env-driven so nothing machine-specific is committed. Values come
// from the shell or a gitignored `.env.local` (loadEnv reads both):
//
//   VITE_HUB_PROXY     hub origin to proxy /api + /ws to (default localhost:4455;
//                      the e2e run points it at its throwaway hub).
//   VITE_ALLOWED_HOSTS comma-separated extra hostnames the dev server accepts —
//                      e.g. an ngrok tunnel. Keep YOUR tunnel out of git by
//                      putting it in web/.env.local, not here.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  // Proxy /api and /ws to the hub so the browser only ever talks to the dev
  // server's origin. Same origin is what lets the HttpOnly SameSite=Strict
  // session cookie travel in dev (and is how prod works, hub-served).
  const HUB = env.VITE_HUB_PROXY ?? "http://localhost:4455";
  const allowedHosts = (env.VITE_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);

  return {
    plugins: [react(), tailwindcss()],
    server: {
      allowedHosts,
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
  };
});
