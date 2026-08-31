"use client"

import React, { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Check, Copy, ExternalLink } from "lucide-react"

interface MarkdownContentProps {
  content: string
  className?: string
}

function CodeBlock({ children, className }: { children: React.ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false)
  const codeText = String(children).replace(/\n$/, "")

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeText)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore clipboard failure
    }
  }

  return (
    <div className="relative my-3 overflow-hidden rounded-xl border border-neutral-200/80 bg-neutral-900 text-neutral-100 dark:border-neutral-800 dark:bg-neutral-950">
      <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900/90 px-3.5 py-1.5 text-xs text-neutral-400">
        <span className="font-mono text-[0.75rem]">{className?.replace("language-", "") || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-white"
        >
          {copied ? (
            <>
              <Check className="size-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="size-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[0.875rem] leading-relaxed text-neutral-200">
        <code>{codeText}</code>
      </pre>
    </div>
  )
}

export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  return (
    <div className={`prose-chat text-[1.03125rem] leading-[1.72] tracking-[-0.012em] text-neutral-800 dark:text-neutral-200 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          a: ({ href, children }) => {
            const isExternal = href?.startsWith("http")
            return (
              <a
                href={href}
                target={isExternal ? "_blank" : undefined}
                rel={isExternal ? "noopener noreferrer" : undefined}
                className="inline-flex max-w-full items-center gap-1 font-medium text-blue-600 underline decoration-blue-300 underline-offset-3 transition-colors hover:text-blue-700 hover:decoration-blue-500 dark:text-blue-400 dark:decoration-blue-700 dark:hover:text-blue-300 break-all"
              >
                <span className="truncate">{children}</span>
                {isExternal && <ExternalLink className="size-3.5 shrink-0 opacity-70" />}
              </a>
            )
          },
          ul: ({ children }) => <ul className="mb-3 ml-5 list-disc space-y-1.5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 ml-5 list-decimal space-y-1.5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="pl-0.5">{children}</li>,
          h1: ({ children }) => (
            <h1 className="mb-3 mt-4 text-[1.375rem] font-semibold tracking-tight text-neutral-900 dark:text-white first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="mb-2.5 mt-3.5 text-[1.2rem] font-semibold tracking-tight text-neutral-900 dark:text-white first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="mb-2 mt-3 text-[1.0625rem] font-semibold tracking-tight text-neutral-900 dark:text-white first:mt-0">
              {children}
            </h3>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-3 border-neutral-300 pl-3.5 italic text-neutral-600 dark:border-neutral-700 dark:text-neutral-400">
              {children}
            </blockquote>
          ),
          code: ({ inline, className, children, ...props }: any) => {
            const isCodeBlock = !inline && (className || String(children).includes("\n"))
            if (isCodeBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>
            }
            return (
              <code
                className="rounded-md border border-neutral-200/80 bg-neutral-100 px-1.5 py-0.5 font-mono text-[0.875em] text-neutral-800 dark:border-neutral-800 dark:bg-neutral-800/80 dark:text-neutral-200"
                {...props}
              >
                {children}
              </code>
            )
          },
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-800">
              <table className="w-full text-left text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-neutral-200 bg-neutral-50 px-3.5 py-2 font-semibold text-neutral-900 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-100">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-neutral-100 px-3.5 py-2 text-neutral-700 last:border-0 dark:border-neutral-800/60 dark:text-neutral-300">
              {children}
            </td>
          ),
          hr: () => <hr className="my-4 border-neutral-200 dark:border-neutral-800" />,
          strong: ({ children }) => <strong className="font-semibold text-neutral-900 dark:text-white">{children}</strong>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
