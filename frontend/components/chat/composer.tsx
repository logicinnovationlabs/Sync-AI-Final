"use client"

import { useRef, useState } from "react"
import { ArrowUp } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * The composer.
 *
 * A textarea that grows with its content up to a cap, not an <input> — questions
 * here run to a sentence or two and a single-line field that scrolls sideways
 * hides what you just typed. Enter sends, Shift+Enter breaks the line.
 */
export function Composer({
  onSend,
  disabled,
  placeholder = "Ask about your invoices, chats, files or ledgers…",
}: {
  onSend: (text: string) => void
  disabled?: boolean
  placeholder?: string
}) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  function resize() {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  function submit() {
    const text = value.trim()
    if (!text || disabled) return
    setValue("")
    if (ref.current) ref.current.style.height = "auto"
    onSend(text)
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
      className="relative flex items-end gap-2 rounded-[1.75rem] border border-border bg-card p-2 pl-4 shadow-[0_2px_24px_-16px_oklch(0.3_0.04_275/0.5)] transition-colors focus-within:border-foreground/25"
    >
      <label htmlFor="composer" className="sr-only">
        Ask a question
      </label>
      <textarea
        id="composer"
        ref={ref}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value)
          resize()
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
        className="max-h-40 min-h-[2.25rem] flex-1 resize-none self-center bg-transparent py-2 text-[0.9375rem] leading-6 outline-none placeholder:text-muted-foreground/70 disabled:opacity-60"
      />

      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="Send"
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-full transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          value.trim() && !disabled
            ? "bg-primary text-primary-foreground hover:bg-primary/85"
            : "bg-muted text-muted-foreground"
        )}
      >
        <ArrowUp className="size-4" />
      </button>
    </form>
  )
}
