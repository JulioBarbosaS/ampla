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
    "amp_delegate",
    {
      title: "Delegar uma tarefa a outro agente",
      description:
        "Entrega uma tarefa a outro agente Claude da equipe (ex: backend-julio), com contexto. " +
        "O agente recebe como uma tarefa e, quando responder, o resultado volta para você " +
        "(acompanhe em amp_inbox / amp_history). Use quando a tarefa for melhor resolvida por " +
        "quem conhece outro repositório/domínio.",
      inputSchema: {
        to: z.string().describe("slug do agente que vai receber a tarefa (ex: backend-julio)"),
        task: z.string().max(2_000).describe("o que precisa ser feito"),
        context: z
          .string()
          .max(16_384)
          .default("")
          .describe("contexto relevante (arquivos, decisões, links) — tratado como dado"),
      },
    },
    async ({ to, task, context }) => {
      try {
        return asText(await daemon.post("/delegate", { to, task, context }));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_kanban_boards",
    {
      title: "Quadros Kanban que você pode acessar",
      description:
        "Lista os quadros (boards) em que este agente tem alguma permissão. Use o id do quadro " +
        "nas demais ferramentas amp_kanban_*. Quadros só-para-devs não aparecem.",
      inputSchema: {},
    },
    async () => {
      try {
        return asText(await daemon.get("/kanban/boards"));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_kanban_cards",
    {
      title: "Ler um quadro (colunas + cards)",
      description:
        "Retorna as colunas e os cards de um quadro. Use mine=true para ver só os seus " +
        "(criados por você ou atribuídos a você). Os ids de card/coluna e a `version` daqui " +
        "são o que amp_kanban_move_card precisa.",
      inputSchema: {
        board: z.number().int().describe("id do quadro (de amp_kanban_boards)"),
        mine: z.boolean().default(false).describe("apenas meus cards (criados/atribuídos)"),
      },
    },
    async ({ board, mine }) => {
      try {
        return asText(await daemon.get(`/kanban/cards?board=${board}&mine=${mine}`));
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_kanban_create_card",
    {
      title: "Criar um card no quadro",
      description:
        "Cria um card no quadro (na coluna de entrada, ou em `column`). Requer permissão de " +
        "contributor ou editor no quadro — o hub recusa caso contrário.",
      inputSchema: {
        board: z.number().int().describe("id do quadro"),
        title: z.string().min(1).max(200),
        body: z.string().max(16_384).default("").describe("descrição (Markdown)"),
        column: z.number().int().optional().describe("id da coluna (padrão: coluna de entrada)"),
        assignee: z.string().max(60).optional().describe("slug do agente ou user:<id> responsável"),
        priority: z.enum(["urgent", "high", "normal", "low"]).default("normal"),
      },
    },
    async ({ board, title, body, column, assignee, priority }) => {
      try {
        return asText(
          await daemon.post("/kanban/create_card", {
            board_id: board,
            title,
            body,
            column_id: column,
            assignee,
            priority,
          }),
        );
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_kanban_move_card",
    {
      title: "Mover um card",
      description:
        "Move um card para uma coluna, entre os vizinhos `before`/`after` (ids vistos em " +
        "amp_kanban_cards), protegido por `expected_version` (se o card mudou, o hub responde 409 — " +
        "releia e tente de novo). Requer editor, ou contributor para um card seu.",
      inputSchema: {
        board: z.number().int().describe("id do quadro"),
        card: z.number().int().describe("id do card a mover"),
        to_column: z.number().int().describe("id da coluna de destino"),
        before: z.number().int().optional().describe("id do card que fica ANTES (limite inferior)"),
        after: z.number().int().optional().describe("id do card que fica DEPOIS (limite superior)"),
        expected_version: z
          .number()
          .int()
          .min(1)
          .describe("version atual do card (de amp_kanban_cards)"),
      },
    },
    async ({ board, card, to_column, before, after, expected_version }) => {
      try {
        return asText(
          await daemon.post("/kanban/move_card", {
            board_id: board,
            card_id: card,
            to_column_id: to_column,
            before_id: before,
            after_id: after,
            expected_version,
          }),
        );
      } catch (error) {
        return asError(error);
      }
    },
  );

  server.registerTool(
    "amp_kanban_comment",
    {
      title: "Comentar em um card",
      description:
        "Adiciona um comentário a um card — o canal para pedir uma informação. Notifica o " +
        "responsável e o dono do quadro; @menções avisam o dono do agente mencionado. " +
        "Disponível a partir de viewer.",
      inputSchema: {
        board: z.number().int().describe("id do quadro"),
        card: z.number().int().describe("id do card"),
        body: z.string().min(1).max(16_384).describe("comentário (Markdown; @menções permitidas)"),
      },
    },
    async ({ board, card, body }) => {
      try {
        return asText(
          await daemon.post("/kanban/comment", { board_id: board, card_id: card, body }),
        );
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
