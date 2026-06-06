/**
 * Golden/snapshot dos componentes centrais do chat — mudanças de
 * markup/classes aparecem em diff de code review (vitest -u atualiza).
 */

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Message } from "../../lib/api/types";
import { useChatStore } from "../../stores/chat";
import { MessageBubble } from "./ChatWindow";
import { Sidebar } from "./Sidebar";

vi.mock("../../lib/api/agents", () => ({
  agentsApi: {
    mine: vi.fn().mockResolvedValue([]),
  },
}));

const MESSAGE: Message = {
  id: 1,
  from: "mobile-eduardo",
  to: "backend-julio",
  body: "Existe endpoint de reset de senha?",
  created_at: "2026-06-06T15:30:00Z",
  delivered_at: "2026-06-06T15:30:01Z",
};

beforeEach(() => {
  useChatStore.setState({
    perspective: "backend-julio",
    partner: null,
    directory: [
      { slug: "backend-julio", display_name: "Backend", online: true },
      { slug: "mobile-eduardo", display_name: "Mobile do Eduardo", online: false },
    ],
    online: { "backend-julio": true, "mobile-eduardo": false },
    conversations: {},
  });
});

describe("snapshots", () => {
  it("MessageBubble recebida", () => {
    const { container } = render(<MessageBubble message={MESSAGE} mine={false} />);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("MessageBubble enviada (entregue)", () => {
    const { container } = render(<MessageBubble message={MESSAGE} mine />);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("Sidebar com equipe e presença", () => {
    const { container } = render(<Sidebar />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
