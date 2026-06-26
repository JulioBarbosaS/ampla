/**
 * `amp <agent> install-service` — write a systemd --user unit so an agent's
 * daemon survives logout, reboot and crashes (instead of "leave it in tmux").
 *
 * The unit runs `amp <agent> on`, which runs the daemon via tsx from src/ — so
 * the service always starts from the current code, never a stale dist/ build.
 */

import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const BRIDGE_DIR = resolve(import.meta.dirname, "../..");
const SLUG_RE = /^[a-z][a-z0-9-]{1,48}[a-z0-9]$/;

/** The systemd --user unit text. Pure (no I/O) so it is unit-tested directly. */
export function buildServiceUnit(opts: {
  agent: string;
  nodeBin: string;
  ampScript: string;
}): string {
  return `[Unit]
Description=Ampla daemon — ${opts.agent}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${opts.nodeBin} ${opts.ampScript} ${opts.agent} on
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
`;
}

export function run(argv: string[]): void {
  const agent = argv[0] ?? "";
  if (!SLUG_RE.test(agent)) {
    throw new Error(`Slug de agente inválido: ${agent || "(vazio)"}`);
  }
  const home = join(homedir(), ".amp", agent);
  if (!existsSync(join(home, "config.json"))) {
    throw new Error(`Agente "${agent}" não conectado. Conecte primeiro: amp connect <token>`);
  }
  const unit = buildServiceUnit({
    agent,
    nodeBin: process.execPath,
    ampScript: join(BRIDGE_DIR, "bin", "amp.mjs"),
  });
  const dir = join(homedir(), ".config", "systemd", "user");
  mkdirSync(dir, { recursive: true });
  const path = join(dir, `amp-${agent}.service`);
  writeFileSync(path, unit);

  console.error(`✓ serviço escrito → ${path}`);
  console.error("Ative (sobe agora e a cada boot):");
  console.error("    systemctl --user daemon-reload");
  console.error(`    systemctl --user enable --now amp-${agent}`);
  console.error("Para que rode sem você estar logado:");
  console.error("    sudo loginctl enable-linger $USER");
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    run(process.argv.slice(2));
  } catch (error) {
    console.error(`[amp install-service] ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }
}
