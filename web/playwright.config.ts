import { defineConfig } from "@playwright/test";

/**
 * E2E contra hub REAL: sobe o uvicorn (porta 8021, banco descartável)
 * e o vite dev (porta 5273) antes dos testes.
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
        AMP_CORS_ORIGINS: '["http://localhost:5273"]',
      },
    },
    {
      command: "pnpm dev --port 5273 --strictPort",
      url: "http://localhost:5273",
      reuseExistingServer: false,
      env: {
        VITE_HUB_URL: "http://localhost:8021",
      },
    },
  ],
});
