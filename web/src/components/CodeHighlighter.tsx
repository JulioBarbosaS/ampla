import { PrismAsyncLight as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

/**
 * The Prism highlighter is heavy (~60 KB gz) and only needed when a message
 * actually contains a code fence, so it lives in its own module and is
 * lazy-loaded by `Markdown` — keeping it out of the initial bundle (login, etc.).
 */
export default function CodeHighlighter({ code, language }: { code: string; language?: string }) {
  return (
    <SyntaxHighlighter
      language={language}
      style={oneDark}
      PreTag="div"
      customStyle={{
        margin: 0,
        background: "transparent",
        fontSize: "0.78rem",
        padding: "0.6rem 0.75rem",
      }}
    >
      {code}
    </SyntaxHighlighter>
  );
}
