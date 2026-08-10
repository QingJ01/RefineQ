"use client";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";


export function normalizeMathDelimiters(value: string): string {
  return value
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, expression: string) => `\n$$\n${expression.trim()}\n$$\n`)
    .replace(/\\\((.+?)\\\)/g, (_match, expression: string) => `$${expression.trim()}$`);
}

export function RichText({
  children,
  className = "",
}: {
  children: string;
  className?: string;
}) {
  return (
    <div className={`rich-text ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ children: linkText, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{linkText}</a>
          ),
          img: ({ alt }) => <span className="rich-text-image-label">{alt || "Image"}</span>,
        }}
      >
        {normalizeMathDelimiters(children)}
      </ReactMarkdown>
    </div>
  );
}
