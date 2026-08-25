"use client"

import { useRef, useState } from "react"
import { ArrowUp, Square } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * The composer.
 *
 * A textarea that grows with its content up to a cap, not an <input> — questions
 * here run to a sentence or two and a single-line field that scrolls sideways
 * hides what you just typed. Enter sends, Shift+Enter breaks the line.
 * While a reply is streaming, the send control becomes Stop.
 */
export function Composer({
  onSend,
  onStop,
  disabled,
  busy,
  placeholder = "Ask about your invoices, chats, files or ledgers…",
}: {
  onSend: (text: string) => void
  onStop?: () => void
  disabled?: boolean
  busy?: boolean
  placeholder?: string
}) {
  const [value, setValue] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)

  function resize() {
    const el = ref.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  function submit() {
    const text = value.trim()
    if (!text || disabled || busy) return
    setValue("")
    if (ref.current) ref.current.style.height = "auto"
    onSend(text)
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (busy) {
          onStop?.()
          return
        }
        submit()
      }}
      className="relative flex items-end gap-2 rounded-[1.75rem] border border-neutral-200/90 bg-card px-2 py-2 pl-4 shadow-[0_1px_2px_oklch(0.35_0.02_275/0.04),0_8px_28px_-18px_oklch(0.3_0.03_275/0.28)] transition-colors focus-within:border-neutral-300"
    >
      <label htmlFor="composer" className="sr-only">
        Ask a question
      </label>
      <textarea
        id="composer"
        ref={ref}
        rows={1}
        value={value}
        disabled={disabled && !busy}
        placeholder={placeholder}
        onChange={(event) => {
          setValue(event.target.value)
          resize()
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault()
            if (!busy) submit()
          }
        }}
        className="max-h-44 min-h-[2.75rem] flex-1 resize-none self-center bg-transparent py-2.5 text-[1rem] leading-[1.55] tracking-[-0.011em] text-neutral-800 outline-none placeholder:text-neutral-400 disabled:opacity-60"
      />

      {busy ? (
        <button
          type="button"
          onClick={() => onStop?.()}
          aria-label="Stop generating"
          className="mb-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-neutral-800 text-white transition-all outline-none hover:bg-neutral-700 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Square className="size-3.5 fill-current" />
        </button>
      ) : (
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className={cn(
            "mb-0.5 grid size-9 shrink-0 place-items-center rounded-full transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            value.trim() && !disabled
              ? "bg-neutral-800 text-white hover:bg-neutral-700"
              : "bg-neutral-100 text-neutral-400"
          )}
        >
          <ArrowUp className="size-4" />
        </button>
      )}
    </form>
  )
}
