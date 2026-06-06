/**
 * Cliente HTTP do MCP para a API local do daemon (unix socket 0600).
 * O MCP é stateless — todo estado vive no daemon (docs/ARCHITECTURE.md).
 */

import { Client } from "undici";
import { socketPath } from "../shared/config.js";

export class DaemonClient {
  private readonly client: Client;

  constructor(path: string = socketPath()) {
    this.client = new Client("http://daemon.local", { socketPath: path });
  }

  async get(path: string): Promise<unknown> {
    return this.request("GET", path);
  }

  async post(path: string, body: unknown): Promise<unknown> {
    return this.request("POST", path, body);
  }

  private async request(method: "GET" | "POST", path: string, body?: unknown): Promise<unknown> {
    let response;
    try {
      response = await this.client.request({
        method,
        path,
        ...(body !== undefined
          ? {
              headers: { "content-type": "application/json" },
              body: JSON.stringify(body),
            }
          : {}),
      });
    } catch {
      throw new Error(
        "Daemon AMP não está rodando. Inicie com `pnpm daemon` (no diretório bridge/) e tente de novo."
      );
    }
    const text = await response.body.text();
    const payload = text ? JSON.parse(text) : {};
    if (response.statusCode >= 400) {
      const detail =
        typeof payload === "object" && payload !== null && "error" in payload
          ? String((payload as { error: unknown }).error)
          : `HTTP ${response.statusCode}`;
      throw new Error(detail);
    }
    return payload;
  }

  async close(): Promise<void> {
    await this.client.close();
  }
}
