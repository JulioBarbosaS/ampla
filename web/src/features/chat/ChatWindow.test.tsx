import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";
import { ChatWindow, MessageBubble } from "./ChatWindow";

function msg(
  id: number,
  from: string,
  to: string,
  body: string,
  over: Partial<Message> = {},
): Message {
  return {
    id,
    from,
    to,
    body,
    created_at: "2026-06-06T15:30:00Z",
    type: "request",
    priority: "normal",
    group: null,
    thread_id: id,
    in_reply_to: null,
    delivered_at: id % 2 === 0 ? "2026-06-06T15:30:01Z" : null,
    expires_at: null,
    ...over,
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

  it("chip 🤖 auto quando o corpo começa com [auto] e esconde o prefixo", () => {
    render(
      <MessageBubble
        message={msg(2, "backend-julio", "mobile-eduardo", "[auto] Sim, existe.", {
          type: "response",
        })}
        mine
      />,
    );
    expect(screen.getByText(/🤖 auto/)).toBeInTheDocument();
    expect(screen.getByText("Sim, existe.")).toBeInTheDocument();
    expect(screen.queryByText(/\[auto\]/)).not.toBeInTheDocument();
  });

  it("chip via @grupo quando a mensagem veio de um broadcast", () => {
    render(
      <MessageBubble
        message={msg(1, "infra-maria", "backend-julio", "deploy às 18h", {
          group: "@frontend-team",
          type: "notification",
        })}
        mine={false}
      />,
    );
    expect(screen.getByText(/via @frontend-team/)).toBeInTheDocument();
  });

  it("mostra citação compacta da mensagem-mãe", () => {
    const parent = msg(1, "mobile-eduardo", "backend-julio", "existe reset de senha?");
    render(
      <MessageBubble
        message={msg(2, "backend-julio", "mobile-eduardo", "não há", {
          type: "response",
          in_reply_to: 1,
        })}
        mine
        repliedTo={parent}
      />,
    );
    expect(screen.getByText(/existe reset de senha\?/)).toBeInTheDocument();
  });

  it("marca pergunta como respondida quando answeredBy é passado", () => {
    render(
      <MessageBubble
        message={msg(1, "mobile-eduardo", "backend-julio", "dúvida?", { type: "request" })}
        mine={false}
        answeredBy="backend-julio"
      />,
    );
    expect(screen.getByText(/respondida/)).toBeInTheDocument();
  });

  it("não marca 'respondida' em mensagem que não é pergunta", () => {
    render(
      <MessageBubble
        message={msg(1, "x", "y", "aviso", { type: "notification" })}
        mine={false}
        answeredBy="y"
      />,
    );
    expect(screen.queryByText(/respondida/)).not.toBeInTheDocument();
  });

  it("botão responder dispara onReply com a mensagem", () => {
    const onReply = vi.fn();
    const m = msg(1, "mobile-eduardo", "backend-julio", "pergunta");
    render(<MessageBubble message={m} mine={false} onReply={onReply} />);
    fireEvent.click(screen.getByRole("button", { name: "responder" }));
    expect(onReply).toHaveBeenCalledWith(m);
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

  it("calcula 'respondida' a partir do in_reply_to na conversa", () => {
    useChatStore.setState({
      perspective: "backend-julio",
      partner: "mobile-eduardo",
      online: {},
      conversations: {
        "backend-julio|mobile-eduardo": [
          msg(1, "mobile-eduardo", "backend-julio", "tem reset?", { type: "request" }),
          msg(2, "backend-julio", "mobile-eduardo", "[auto] não", {
            type: "response",
            in_reply_to: 1,
          }),
        ],
      },
      directory: [],
    });
    render(<ChatWindow />);
    // a pergunta (id 1) ganhou indicador, a resposta automática aparece sem prefixo
    expect(screen.getByText(/respondida/)).toBeInTheDocument();
    expect(screen.getByText(/🤖 auto/)).toBeInTheDocument();
  });

  it("expõe seletores de tipo e prioridade no composer", () => {
    useChatStore.setState({
      perspective: "backend-julio",
      partner: "mobile-eduardo",
      online: {},
      conversations: {},
      directory: [],
    });
    render(<ChatWindow />);
    expect(screen.getByLabelText("tipo da mensagem")).toBeInTheDocument();
    expect(screen.getByLabelText("prioridade")).toBeInTheDocument();
  });
});
