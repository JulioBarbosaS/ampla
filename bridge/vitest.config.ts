import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
    testTimeout: 10_000,
    coverage: {
      provider: "v8",
      include: ["src/**"],
      // entrypoint stdio do MCP: composição declarativa, exercitada no uso real
      exclude: ["src/mcp/index.ts"],
      thresholds: {
        lines: 75,
        functions: 75,
        statements: 75,
        branches: 80,
      },
    },
  },
});
