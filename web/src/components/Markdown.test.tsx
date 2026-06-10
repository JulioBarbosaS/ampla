import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Markdown, stripMarkdown } from "./Markdown";

// The real Prism highlighter loads languages async and splits text into spans;
// stub it to a plain <pre> so we test our own wiring (copy button + raw code).
vi.mock("react-syntax-highlighter", () => ({
  PrismAsyncLight: ({ children }: { children: string }) => <pre>{children}</pre>,
}));
vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({ oneDark: {} }));

describe("Markdown", () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it("renders basic markdown (bold, lists, links)", () => {
    render(<Markdown>{"**forte** e [link](https://x.com)\n\n- um\n- dois"}</Markdown>);
    expect(screen.getByText("forte").tagName).toBe("STRONG");
    const link = screen.getByRole("link", { name: "link" });
    expect(link).toHaveAttribute("href", "https://x.com");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders a fenced code block with language + working copy button", async () => {
    render(<Markdown>{"```ts\nconst x = 1;\n```"}</Markdown>);
    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const x = 1;")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "copiar código" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("const x = 1;");
  });

  it("neutralizes dangerous link schemes", () => {
    const { container } = render(<Markdown>{"[x](javascript:alert(1))"}</Markdown>);
    // javascript: is stripped → no usable href (and thus no link role)
    expect(container.querySelector("a")?.getAttribute("href") ?? "").not.toMatch(/javascript:/i);
    expect(screen.getByText("x")).toBeInTheDocument();
  });

  it("does not parse raw HTML and drops remote images", () => {
    const { container } = render(
      <Markdown>{"<script>alert(1)</script> ![x](https://evil/img.png)"}</Markdown>,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    // the raw tag survives as escaped text, not as an element
    expect(screen.getByText(/<script>/)).toBeInTheDocument();
  });
});

describe("stripMarkdown", () => {
  it("flattens markdown to a one-line preview", () => {
    expect(stripMarkdown("**oi** `cmd`\n\n# título")).toBe("oi cmd título");
    expect(stripMarkdown("veja [docs](https://x.com)")).toBe("veja docs");
    expect(stripMarkdown("```\ncode\n```")).toBe("código");
  });
});
