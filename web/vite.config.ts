/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
