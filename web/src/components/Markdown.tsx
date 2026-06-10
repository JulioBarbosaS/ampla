import { lazy, Suspense, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

// Lazy so the heavy Prism highlighter stays out of the initial bundle.
const CodeHighlighter = lazy(() => import("./CodeHighlighter"));

/**
 * Renders an untrusted message body as Markdown. Hard rules (see
 * docs/specs/01-messaging-ux.md): no raw HTML (react-markdown doesn't parse it
 * unless rehype-raw is added — we never add it), link schemes restricted to
 * http(s)/mailto/relative, and no remote images (an SSRF/tracking vector via
 * message bodies). Code fences become copyable, highlighted blocks.
 */

const SAFE_URL = /^(https?:|mailto:)/i;

function safeUrl(url: string): string {
  if (SAFE_URL.test(url)) return url;
  if (/^[/#]/.test(url)) return url; // relative path / anchor
  return ""; // strip javascript:, data:, etc.
}

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard blocked — leave the label unchanged
    }
  }

  return (
    <div className="my-2 overflow-hidden rounded-md border border-zinc-700 bg-zinc-950 text-left">
      <div className="flex items-center justify-between border-b border-zinc-800 px-2.5 py-1">
        <span className="font-mono text-[10px] uppercase tracking-wide text-zinc-500">
          {language ?? "código"}
        </span>
        <button
          type="button"
          onClick={copy}
          aria-label="copiar código"
          className="text-[10px] text-zinc-400 transition-colors hover:text-zinc-200"
        >
          {copied ? "copiado" : "copiar"}
        </button>
      </div>
      <Suspense
        fallback={
          <pre className="m-0 overflow-x-auto px-3 py-2.5 font-mono text-[0.78rem] text-zinc-200">
            {code}
          </pre>
        }
      >
        <CodeHighlighter code={code} language={language} />
      </Suspense>
    </div>
  );
}

const components: Components = {
  // Unwrap <pre> so a code block renders our own container at block level.
  pre({ children }) {
    return <>{children}</>;
  },
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? "");
    const raw = String(children ?? "");
    const isBlock = Boolean(match) || raw.includes("\n");
    if (!isBlock) {
      return (
        <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em]" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock code={raw.replace(/\n$/, "")} language={match?.[1]} />;
  },
  a({ children, href }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    );
  },
  // No remote images in v1 (tracking/SSRF via message bodies).
  img() {
    return null;
  },
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="amp-md break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        urlTransform={safeUrl}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

/** Flatten markdown to a one-line plain string for previews/quotes. */
export function stripMarkdown(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " código ") // fenced code blocks
    .replace(/`([^`]+)`/g, "$1") // inline code
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " imagem ") // images
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // links → their text
    .replace(/[*_~>#]/g, "") // emphasis / heading / quote markers
    .replace(/\s+/g, " ")
    .trim();
}
