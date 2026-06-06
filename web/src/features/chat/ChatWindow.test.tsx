import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import type { Message } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";
import { ChatWindow, MessageBubble } from "./ChatWindow";

function msg(id: number, from: string, to: string, body: string): Message {
  return {
    id,
    from,
    to,
    body,
    created_at: "2026-06-06T15:30:00Z",
    delivered_at: id % 2 === 0 ? "2026-06-06T15:30:01Z" : null,
  };
}

beforeEach(() => {
  useChatStore.setState({
    perspective: null,
    partner: null,
    directory: [],
    online: {},
    conversations: {},
  });
});

describe("MessageBubble", () => {
  it("mostra corpo e estado de entrega das minhas mensagens", () => {
    render(<MessageBubble message={msg(2, "backend-julio", "mobile-eduardo", "olá!")} mine />);
    expect(screen.getByText("olá!")).toBeInTheDocument();
    expect(screen.getByText(/entregue/)).toBeInTheDocument();
  });

  it("mensagem pendente indica pendente", () => {
    render(<MessageBubble message={msg(1, "backend-julio", "mobile-eduardo", "oi")} mine />);
    expect(screen.getByText(/pendente/)).toBeInTheDocument();
  });
});

describe("ChatWindow", () => {
  it("sem seleção mostra orientação", () => {
    render(<ChatWindow />);
    expect(screen.getByText(/Selecione um agente/)).toBeInTheDocument();
  });

  it("renderiza a conversa selecionada na ordem", () => {
    useChatStore.setState({
      perspective: "backend-julio",
      partner: "mobile-eduardo",
      online: { "mobile-eduardo": true },
      conversations: {
        "backend-julio|mobile-eduardo": [
          msg(1, "mobile-eduardo", "backend-julio", "Existe endpoint de reset?"),
          msg(2, "backend-julio", "mobile-eduardo", "Sim: POST /auth/password-reset"),
        ],
      },
      directory: [],
    });
    render(<ChatWindow />);
    expect(screen.getByText("Existe endpoint de reset?")).toBeInTheDocument();
    expect(screen.getByText("Sim: POST /auth/password-reset")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "mobile-eduardo" })).toBeInTheDocument();
  });
});
