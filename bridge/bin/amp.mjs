#!/usr/bin/env node
/**
 * `amp` — thin bridge wrapper. Dispatches subcommands to the entries
 * via the local tsx (runs from src/, no build). Install globally with:
 *   cd bridge && pnpm link --global      # then: amp connect <token>
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ENTRIES = {
  connect: "src/cli/connect.ts",
  daemon: "src/daemon/index.ts",
  mcp: "src/mcp/index.ts",
};

const [sub, ...rest] = process.argv.slice(2);
const entry = sub ? ENTRIES[sub] : undefined;
if (!entry) {
  console.error("Uso: amp <connect|daemon|mcp> [args]");
  console.error("  amp connect <token>   conecta um agente (config + MCP + hooks)");
  console.error("  amp daemon            roda o daemon (use AMP_HOME=~/.amp/<agente>)");
  console.error("  amp mcp               roda o servidor MCP (normalmente via claude mcp)");
  process.exit(sub ? 1 : 0);
}

const tsx = resolve(PKG, "node_modules/.bin/tsx");
const bin = existsSync(tsx) ? tsx : "tsx"; // fallback to tsx on PATH
const result = spawnSync(bin, [resolve(PKG, entry), ...rest], { stdio: "inherit" });
process.exit(result.status ?? 1);
