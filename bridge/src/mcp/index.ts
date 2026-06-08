/**
 * Ampla MCP server — exposes the messaging tools to Claude Code.
 * Stateless: everything is delegated to the daemon over a unix socket.
 */

import { pathToFileURL } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { DaemonClient } from "./daemon-client.js";

const daemon = new DaemonClient();

function asText(payload: unknown): { content: Array<{ type: "text"; text: string }> } {
  return { content: [{ type: "text", text: JSON.stringify(payload, null, 2) }] };
}

function asError(error: unknown): {
  content: Array<{ type: "text"; text: string }>;
  isError: true;
} {
  const message = error instanceof Error ? error.message : String(error);
  return { content: [{ type: "text", text: `Erro: ${message}` }], isError: true };
}

export function buildServer(): McpServer {
  const server = new McpServer({ name: "ampla", version: "0.1.0" });

  server.registerTool(
    "amp_send",
    {
      title: "Enviar mensagem a outro agente ou grupo",
      description:
        "Envia uma mensagem direta para outro agente Claude da equipe (ex: backend-julio), " +
        "para um grupo (ex: @frontend-team) ou para todos (@all). " +
        "Se um destinatário estiver offline, o hub entrega quando ele reconectar.",
      inputSchema: {
        to: z.string().describe("agente (backend-julio), grupo (@frontend-team) ou todos (@all)"),
        body: z.string().max(16_384).describe("conteúdo da mensagem"),
        type: z
          .enum(["request", "response", "notification", "task", "alert", "status", "ack"])
          .default("request")
          .describe("semântica da mensagem: request/task disparam auto-resposta do destinatário"),
        priority: z.enum(["urgent", "high", "normal", "low"]).default("normal"),
        in_reply_to: z
          .number()
          .int()
          .optional()
          .describe("id da mensagem sendo respondida (threading)"),
      },
    },
    async ({ to, body, type, priority, in_reply_to }) => {
      try {
        return asText(await daemon.post("/send", { to, body, type, priority, in_reply_to }));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_inbox",
    {
      title: "Ler mensagens recebidas",
      description:
        "Lista mensagens recebidas de outros agentes. Por padrão retorna só as não lidas e as marca como lidas.",
      inputSchema: {
        unread_only: z.boolean().default(true).describe("apenas não lidas"),
        mark_read: z.boolean().default(true).describe("marcar como lidas ao retornar"),
      },
    },
    async ({ unread_only, mark_read }) => {
      try {
        return asText(await daemon.get(`/inbox?unread_only=${unread_only}&mark_read=${mark_read}`));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_history",
    {
      title: "Histórico de conversa",
      description: "Últimas mensagens trocadas com um agente específico.",
      inputSchema: {
        with: z.string().describe("slug do outro agente"),
        limit: z.number().int().min(1).max(200).default(50),
      },
    },
    async ({ with: partner, limit }) => {
      try {
        return asText(
          await daemon.get(`/history?with=${encodeURIComponent(partner)}&limit=${limit}`),
        );
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_groups",
    {
      title: "Grupos da equipe",
      description:
        "Lista os grupos de agentes e seus membros — destinos válidos para amp_send com @grupo.",
      inputSchema: {},
    },
    async () => {
      try {
        return asText(await daemon.get("/groups"));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_presence",
    {
      title: "Quem está online",
      description: "Lista os agentes da equipe conectados ao hub neste momento.",
      inputSchema: {},
    },
    async () => {
      try {
        return asText(await daemon.get("/presence"));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_status",
    {
      title: "Status do meu agente",
      description:
        "Estado da conexão com o hub, settings atuais (modo auto/inbox) e mensagens não lidas.",
      inputSchema: {},
    },
    async () => {
      try {
        return asText(await daemon.get("/status"));
      } catch (error) {
        return asError(error);
      }
    },
  );

  return server;
}

async function main(): Promise<void> {
  await buildServer().connect(new StdioServerTransport());
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  main().catch((error) => {
    console.error(`[amp-mcp] erro fatal: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  });
}
