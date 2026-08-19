"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { CiteMark } from "@/components/landing/cite-mark"
import { Composer } from "@/components/chat/composer"
import { SourceCard, type SourceCardData } from "@/components/chat/source-card"
import { Loader } from "@/components/motion/loader"
import { streamAssistantChat, type AssistantCitation } from "@/lib/api/assistant"
import { ApiError } from "@/lib/api/client"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { EASE_OUT } from "@/lib/ease"

type Turn =
  | { kind: "user"; id: number; text: string }
  | {
      kind: "answer"
      id: number
      text: string
      sources: SourceCardData[]
      error?: string
      settled: boolean
    }

function citationsToSources(citations: AssistantCitation[]): SourceCardData[] {
  return citations.map((c, i) => ({
    n: i + 1,
    title: c.document_id || `Source ${i + 1}`,
    snippet: c.quote || "",
    meta:
      c.score != null && Number.isFinite(c.score)
        ? `score ${Number(c.score).toFixed(3)}`
        : "Block L citation",
  }))
}

export function ChatView() {
  const reduce = useReducedMotion()
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const claims = useAuthStore((s) => s.claims)
  const authenticated = useAuthStore((s) => s.isAuthenticated())
  const [turns, setTurns] = useState<Turn[]>([])
  const [activeCite, setActiveCite] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const nextId = useRef(0)
  const sessionId = useRef(
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `sess-${Date.now()}`
  )
  const bottomRef = useRef<HTMLDivElement>(null)

  const last = turns[turns.length - 1]
  const busy = last?.kind === "answer" && !last.settled

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "end",
    })
  }, [turns, reduce])

  const ask = useCallback(
    async (text: string) => {
      if (!token || !authenticated) {
        setError("Sign in to chat against the live assistant.")
        return
      }
      setError(null)
      setActiveCite(null)
      const userId = nextId.current++
      const answerId = nextId.current++
      setTurns((prev) => [
        ...prev,
        { kind: "user", id: userId, text },
        { kind: "answer", id: answerId, text: "", sources: [], settled: false },
      ])

      try {
        await streamAssistantChat({
          token,
          prompt: text,
          sessionId: sessionId.current,
          tenantId: claims?.tenant_id,
          onEvent: (event) => {
            if (event.type === "token") {
              setTurns((prev) =>
                prev.map((t) =>
                  t.kind === "answer" && t.id === answerId
                    ? { ...t, text: t.text + event.text }
                    : t
                )
              )
            }
            if (event.type === "final") {
              setTurns((prev) =>
                prev.map((t) =>
                  t.kind === "answer" && t.id === answerId
                    ? {
                        ...t,
                        text: event.response_text || t.text,
                        sources: citationsToSources(event.citations || []),
                        settled: true,
                      }
                    : t
                )
              )
            }
          },
        })
        setTurns((prev) =>
          prev.map((t) =>
            t.kind === "answer" && t.id === answerId && !t.settled
              ? { ...t, settled: true }
              : t
          )
        )
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "Chat request failed."
        setTurns((prev) =>
          prev.map((t) =>
            t.kind === "answer" && t.id === answerId
              ? { ...t, error: message, settled: true }
              : t
          )
        )
      }
    },
    [authenticated, claims?.tenant_id, token]
  )

  const railTurn = [...turns]
    .reverse()
    .find(
      (t): t is Extract<Turn, { kind: "answer" }> =>
        t.kind === "answer" && t.sources.length > 0
    )
  const railSources = railTurn?.sources ?? []
  const empty = turns.length === 0

  // Persist rehydrates from localStorage on the client only. SSR and the
  // first client paint must share one tree (`useAuthHydrated` server
  // snapshot is false) or logged-in users hydrate as "Sign in to chat".
  if (!hydrated) {
    return <div className="flex h-full min-h-0" />
  }

  if (!authenticated) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-lg font-medium">Sign in to chat</p>
        <p className="max-w-md text-sm text-muted-foreground">
          Chat talks to Block L at POST /assistant/orchestrator/chat. There
          is no scripted fallback in the product surface.
        </p>
        <Link
          href="/login?next=/chat"
          className="text-sm text-ink-blue underline-offset-4 hover:underline"
        >
          Sign in
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {empty ? (
            <div className="mx-auto flex max-w-2xl flex-col gap-3 pt-16">
              <h2 className="font-heading text-3xl font-normal tracking-[-0.02em]">
                What do you want to know?
              </h2>
              <p className="text-sm text-muted-foreground">
                Answers come from the live assistant (Block L) with citations from
                retrieved documents.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-2xl flex-col gap-6">
              {turns.map((turn) =>
                turn.kind === "user" ? (
                  <motion.div
                    key={turn.id}
                    initial={reduce ? false : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, ease: EASE_OUT }}
                    className="flex justify-end"
                  >
                    <div className="max-w-[85%] rounded-2xl bg-muted px-4 py-2 text-[0.9375rem]">
                      {turn.text}
                    </div>
                  </motion.div>
                ) : (
                  <AnswerTurn
                    key={turn.id}
                    turn={turn}
                    activeCite={activeCite}
                    setActiveCite={setActiveCite}
                    reduce={!!reduce}
                  />
                )
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="border-t border-border-subtle px-6 py-4">
          <div className="mx-auto max-w-2xl">
            <Composer onSend={ask} disabled={busy} />
            {error && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                {error}
              </p>
            )}
            <p className="mt-2 text-[0.6875rem] text-muted-foreground">
              Live Block L — POST /assistant/orchestrator/chat
            </p>
          </div>
        </div>
      </div>

      <aside className="hidden w-80 shrink-0 border-l border-border-subtle xl:block">
        <div className="px-4 py-4 text-xs font-medium text-muted-foreground">
          Sources · {railSources.length}
        </div>
        {railSources.length === 0 ? (
          <p className="px-4 text-sm text-muted-foreground">
            Records cited in an answer show up here.
          </p>
        ) : (
          <ul className="flex flex-col gap-2 px-3 pb-4">
            {railSources.map((source) => (
              <li key={`${railTurn?.id}-${source.n}`}>
                <SourceCard
                  source={source}
                  active={activeCite === source.n}
                  onActivate={setActiveCite}
                  onDeactivate={() => setActiveCite(null)}
                />
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  )
}

function AnswerTurn({
  turn,
  activeCite,
  setActiveCite,
  reduce,
}: {
  turn: Extract<Turn, { kind: "answer" }>
  activeCite: number | null
  setActiveCite: (n: number | null) => void
  reduce: boolean
}) {
  const streaming = !turn.settled && !turn.error

  return (
    <div className="flex flex-col gap-3">
      <AnimatePresence>
        {!turn.settled && !turn.text && !turn.error && (
          <motion.p
            key="retrieving"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="flex items-center gap-2.5 text-[0.9375rem] text-muted-foreground"
          >
            <Loader size={16} />
            Searching connected sources…
          </motion.p>
        )}
      </AnimatePresence>

      {turn.error && (
        <p role="alert" className="text-sm text-destructive">
          {turn.error}
        </p>
      )}

      {turn.text && (
        <p className="text-[0.9375rem] leading-7">
          {turn.text}
          {turn.sources.map((source) => (
            <CiteMark
              key={source.n}
              n={source.n}
              active={activeCite === source.n}
              onActivate={() => setActiveCite(source.n)}
              onDeactivate={() => setActiveCite(null)}
            />
          ))}
          {streaming && (
            <motion.span
              aria-hidden
              animate={{ opacity: [1, 0.25, 1] }}
              transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut" }}
              className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[0.18em] rounded-full bg-ink-blue"
            />
          )}
        </p>
      )}

      {turn.sources.length > 0 && turn.settled && (
        <ul className="flex flex-col gap-2 xl:hidden">
          {turn.sources.map((source, i) => (
            <motion.li
              key={source.n}
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, ease: EASE_OUT, delay: i * 0.04 }}
            >
              <SourceCard
                source={source}
                active={activeCite === source.n}
                onActivate={setActiveCite}
                onDeactivate={() => setActiveCite(null)}
              />
            </motion.li>
          ))}
        </ul>
      )}
    </div>
  )
}
