/**
 * Histórico local de mensagens do agente (JSONL append-only, 0600).
 * Recebidas (direction=in) carregam flag de leitura para a inbox.
 */

import { appendFileSync, chmodSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { z } from "zod";
import { messageTypeSchema, prioritySchema } from "../shared/protocol.js";

export const storedMessageSchema = z.object({
  id: z.number().int().nullable(), // id do hub (null para registros locais)
  from: z.string(),
  to: z.string(),
  body: z.string(),
  // defaults preservam compatibilidade com JSONL anterior ao threading
  type: messageTypeSchema.default("request"),
  priority: prioritySchema.default("normal"),
  thread_id: z.number().int().nullable().default(null),
  in_reply_to: z.number().int().nullable().default(null),
  ts: z.string(),
  direction: z.enum(["in", "out"]),
  read: z.boolean(),
});
export type StoredMessage = z.infer<typeof storedMessageSchema>;

export class MessageStore {
  private messages: StoredMessage[] = [];

  constructor(private readonly path: string) {
    this.load();
  }

  private load(): void {
    if (!existsSync(this.path)) {
      writeFileSync(this.path, "", { mode: 0o600 });
      return;
    }
    chmodSync(this.path, 0o600);
    const lines = readFileSync(this.path, "utf-8").split("\n").filter(Boolean);
    for (const line of lines) {
      try {
        this.messages.push(storedMessageSchema.parse(JSON.parse(line)));
      } catch {
        // linha corrompida não derruba o daemon; é pulada
      }
    }
  }

  append(message: StoredMessage): void {
    // dedup por id do hub (reentrega de pendentes após reconnect)
    if (message.id !== null && this.messages.some((m) => m.id === message.id)) {
      return;
    }
    this.messages.push(message);
    appendFileSync(this.path, `${JSON.stringify(message)}\n`, { mode: 0o600 });
  }

  /** Conversa com um parceiro, mais recentes por último (ordem de leitura). */
  conversation(partner: string, limit = 50): StoredMessage[] {
    return this.messages.filter((m) => m.from === partner || m.to === partner).slice(-limit);
  }

  inbox(unreadOnly = true): StoredMessage[] {
    return this.messages.filter((m) => m.direction === "in" && (!unreadOnly || !m.read));
  }

  unreadCount(): number {
    return this.inbox(true).length;
  }

  markRead(ids: Array<number | null>): void {
    const idSet = new Set(ids.filter((i): i is number => i !== null));
    let changed = false;
    for (const m of this.messages) {
      if (m.id !== null && idSet.has(m.id) && !m.read) {
        m.read = true;
        changed = true;
      }
    }
    if (changed) {
      this.rewrite();
    }
  }

  markAllRead(): void {
    let changed = false;
    for (const m of this.messages) {
      if (m.direction === "in" && !m.read) {
        m.read = true;
        changed = true;
      }
    }
    if (changed) {
      this.rewrite();
    }
  }

  partners(): string[] {
    const seen = new Set<string>();
    for (const m of this.messages) {
      seen.add(m.direction === "in" ? m.from : m.to);
    }
    return [...seen].sort();
  }

  private rewrite(): void {
    const content = this.messages.map((m) => JSON.stringify(m)).join("\n");
    writeFileSync(this.path, content ? `${content}\n` : "", { mode: 0o600 });
  }
}
