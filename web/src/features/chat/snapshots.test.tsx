/**
 * Golden/snapshot of the core chat components — markup/class changes
 * show up in the code-review diff (vitest -u updates them).
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

vi.mock("../../lib/api/groups", () => ({
  groupsApi: { list: vi.fn().mockResolvedValue([]) },
}));

vi.mock("../../lib/api/messages", () => ({
  messagesApi: { partners: vi.fn().mockResolvedValue([]) },
}));

const MESSAGE: Message = {
  id: 1,
  from: "mobile-eduardo",
  to: "backend-julio",
  body: "Existe endpoint de reset de senha?",
  created_at: "2026-06-06T15:30:00Z",
  type: "request",
  priority: "normal",
  group: null,
  thread_id: 1,
  in_reply_to: null,
  delivered_at: "2026-06-06T15:30:01Z",
  expires_at: null,
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
  it("MessageBubble received", () => {
    const { container } = render(<MessageBubble message={MESSAGE} mine={false} />);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("MessageBubble sent (delivered)", () => {
    const { container } = render(<MessageBubble message={MESSAGE} mine />);
    expect(container.firstChild).toMatchSnapshot();
  });

  it("Sidebar with team and presence", () => {
    const { container } = render(<Sidebar />);
    expect(container.firstChild).toMatchSnapshot();
  });
});
