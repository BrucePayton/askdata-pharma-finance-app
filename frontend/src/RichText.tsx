import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function CodeBlock({ children, ...props }: { children?: ReactNode }) {
  const child = Children.count(children) === 1 ? Children.only(children) : undefined;
  const className = isValidElement(child)
    ? String((child as ReactElement<{ className?: string }>).props.className || "")
    : "";
  if (/language-(sql|mysql|postgresql|tsql)\b/i.test(className)) {
    return <details className="technical-details"><summary>查看技术查询语句</summary><pre {...props}>{children}</pre></details>;
  }
  return <pre {...props}>{children}</pre>;
}

/** Model text is untrusted: raw HTML stays disabled; Markdown sanitizes URLs. */
export function RichText({ children }: { children: string }) {
  return <div className="rich-text"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
    components={{ a: props => <a {...props} target="_blank" rel="noopener noreferrer" />, pre: CodeBlock }}>{children}</ReactMarkdown></div>;
}
