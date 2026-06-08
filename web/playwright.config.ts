import { defineConfig } from "@playwright/test";

/**
 * E2E contra hub REAL: sobe o uvicorn (porta 8021, banco descartável)
 * e o vite dev (porta 5273) antes dos testes. O Vite faz proxy de /api e /ws
 * para o hub (VITE_HUB_PROXY), então o navegador fala só com :5273 — mesma
 * origem, exigência do cookie de sessão HttpOnly+SameSite=Strict.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:5273",
  },
  webServer: [
    {
      command:
        "rm -f /tmp/amp-e2e.db && ../hub/.venv/bin/python -m uvicorn app.main:app --port 8021",
      cwd: "../hub",
      url: "http://localhost:8021/api/health",
      reuseExistingServer: false,
      env: {
        AMP_DATABASE_URL: "sqlite+aiosqlite:////tmp/amp-e2e.db",
        AMP_JWT_SECRET: "e2e-secret-com-no-minimo-32-bytes!!",
      },
    },
    {
      command: "pnpm dev --port 5273 --strictPort",
      url: "http://localhost:5273",
      reuseExistingServer: false,
      env: {
        // same-origin: the browser hits :5273; Vite proxies /api and /ws here
        VITE_HUB_PROXY: "http://localhost:8021",
      },
    },
  ],
});
