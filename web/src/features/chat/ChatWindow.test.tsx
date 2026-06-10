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
  it("shows body and delivery state for my messages", () => {
    render(<MessageBubble message={msg(2, "backend-julio", "mobile-eduardo", "olá!")} mine />);
    expect(screen.getByText("olá!")).toBeInTheDocument();
    expect(screen.getByText(/entregue/)).toBeInTheDocument();
  });

  it("pending message indicates pending", () => {
    render(<MessageBubble message={msg(1, "backend-julio", "mobile-eduardo", "oi")} mine />);
    expect(screen.getByText(/pendente/)).toBeInTheDocument();
  });

  it("shows the 🤖 auto chip when the body starts with [auto] and hides the prefix", () => {
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

  it("shows the via @group chip when the message came from a broadcast", () => {
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

  it("shows a compact quote of the parent message", () => {
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

  it("marks a question as answered when answeredBy is passed", () => {
    render(
      <MessageBubble
        message={msg(1, "mobile-eduardo", "backend-julio", "dúvida?", { type: "request" })}
        mine={false}
        answeredBy="backend-julio"
      />,
    );
    expect(screen.getByText(/respondida/)).toBeInTheDocument();
  });

  it("does not mark as answered on a message that is not a question", () => {
    render(
      <MessageBubble
        message={msg(1, "x", "y", "aviso", { type: "notification" })}
        mine={false}
        answeredBy="y"
      />,
    );
    expect(screen.queryByText(/respondida/)).not.toBeInTheDocument();
  });

  it("shows a TTL chip for a pending message that is expiring", () => {
    const future = new Date(Date.now() + 90 * 60_000).toISOString(); // ~90 min
    render(
      <MessageBubble
        message={msg(1, "x", "backend-julio", "efêmera", { expires_at: future })}
        mine={false}
      />,
    );
    expect(screen.getByText(/expira em/)).toBeInTheDocument();
  });

  it("shows 'expirada' once past expires_at", () => {
    const past = new Date(Date.now() - 60_000).toISOString();
    render(
      <MessageBubble
        message={msg(1, "x", "backend-julio", "velha", { expires_at: past })}
        mine={false}
      />,
    );
    expect(screen.getByText(/expirada/)).toBeInTheDocument();
  });

  it("does not show a TTL chip on a delivered message", () => {
    const future = new Date(Date.now() + 60 * 60_000).toISOString();
    // id 2 → delivered in the helper
    render(
      <MessageBubble
        message={msg(2, "backend-julio", "x", "entregue", { expires_at: future })}
        mine
      />,
    );
    expect(screen.queryByText(/expira/)).not.toBeInTheDocument();
  });

  it("reply button fires onReply with the message", () => {
    const onReply = vi.fn();
    const m = msg(1, "mobile-eduardo", "backend-julio", "pergunta");
    render(<MessageBubble message={m} mine={false} onReply={onReply} />);
    fireEvent.click(screen.getByRole("button", { name: "responder" }));
    expect(onReply).toHaveBeenCalledWith(m);
  });
});

describe("ChatWindow", () => {
  it("shows guidance when nothing is selected", () => {
    render(<ChatWindow />);
    expect(screen.getByText(/Selecione um agente/)).toBeInTheDocument();
  });

  it("renders the selected conversation in order", () => {
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

  it("computes 'answered' from in_reply_to within the conversation", () => {
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
    // the question (id 1) got the indicator, the auto reply shows without the prefix
    expect(screen.getByText(/respondida/)).toBeInTheDocument();
    expect(screen.getByText(/🤖 auto/)).toBeInTheDocument();
  });

  it("exposes type and priority selectors in the composer", () => {
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
