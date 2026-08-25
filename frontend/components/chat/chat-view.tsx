"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { Composer } from "@/components/chat/composer"
import { SourceCard, type SourceCardData } from "@/components/chat/source-card"
import { Loader } from "@/components/motion/loader"
import {
  getAssistantSession,
  listAssistantSessions,
  streamAssistantChat,
  stripInlineCitations,
  type AssistantCitation,
} from "@/lib/api/assistant"
import { ApiError } from "@/lib/api/client"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { useChatSessionStore } from "@/lib/chat/session-store"
import { EASE_OUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

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

type ChatWindow = {
  id: string
  title: string
  updatedAt: number
}

function citationsToSources(citations: AssistantCitation[]): SourceCardData[] {
  return citations.map((c, i) => ({
    n: i + 1,
    title: c.title || c.document_id || `Source ${i + 1}`,
    snippet: c.quote || "",
    meta:
      c.score != null && Number.isFinite(c.score)
        ? `score ${Number(c.score).toFixed(3)}`
        : "Source",
  }))
}

function newSessionId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `sess-${Date.now()}`
}

function storageKey(tenantId: string, userId: string) {
  return `synq.chat.v1.${tenantId}.${userId}`
}

function loadLocalStore(tenantId: string, userId: string): {
  activeId: string
  windows: ChatWindow[]
  turnsById: Record<string, Turn[]>
} {
  const empty = { activeId: newSessionId(), windows: [] as ChatWindow[], turnsById: {} }
  if (typeof window === "undefined") return empty
  try {
    const raw = localStorage.getItem(storageKey(tenantId, userId))
    if (!raw) return empty
    const parsed = JSON.parse(raw) as {
      activeId?: string
      windows?: ChatWindow[]
      turnsById?: Record<string, Turn[]>
    }
    return {
      activeId: parsed.activeId || empty.activeId,
      windows: Array.isArray(parsed.windows) ? parsed.windows : [],
      turnsById: parsed.turnsById && typeof parsed.turnsById === "object" ? parsed.turnsById : {},
    }
  } catch {
    return empty
  }
}

function titleFromTurns(turns: Turn[]): string {
  const first = turns.find((t) => t.kind === "user")
  const text = first?.kind === "user" ? first.text.trim() : ""
  return text ? text.slice(0, 80) : "New chat"
}

function historyToTurns(history: Array<{ role: string; content: string; citations?: AssistantCitation[] }>): Turn[] {
  const turns: Turn[] = []
  let id = 0
  for (const item of history) {
    if (item.role === "user") {
      turns.push({ kind: "user", id: id++, text: item.content })
    } else if (item.role === "assistant") {
      turns.push({
        kind: "answer",
        id: id++,
        text: stripInlineCitations(item.content || ""),
        sources: citationsToSources(item.citations || []),
        settled: true,
      })
    }
  }
  return turns
}

export function ChatView() {
  const reduce = useReducedMotion()
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const claims = useAuthStore((s) => s.claims)
  const authenticated = useAuthStore((s) => s.isAuthenticated())
  const tenantId = claims?.tenant_id || "alpha"
  const userId = claims?.sub || "anon"

  const [turns, setTurns] = useState<Turn[]>([])
  const [windows, setWindows] = useState<ChatWindow[]>([])
  const [sessionId, setSessionId] = useState("")
  const [activeCite, setActiveCite] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const nextId = useRef(0)
  const turnsRef = useRef<Turn[]>([])
  const sessionRef = useRef("")
  const windowsRef = useRef<ChatWindow[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [sourcesOpen, setSourcesOpen] = useState(true)

  turnsRef.current = turns
  sessionRef.current = sessionId
  windowsRef.current = windows

  const last = turns[turns.length - 1]
  const busy = last?.kind === "answer" && !last.settled

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const syncSessionStore = useChatSessionStore((s) => s.sync)
  const clearPending = useChatSessionStore((s) => s.clearPending)
  const pending = useChatSessionStore((s) => s.pending)

  useEffect(() => {
    if (!ready) return
    syncSessionStore({
      sessionId,
      windows,
      activeTurnCount: turns.length,
      ready: true,
    })
  }, [ready, sessionId, syncSessionStore, turns.length, windows])

  const persist = useCallback(
    (nextSession: string, nextTurns: Turn[], nextWindows: ChatWindow[]) => {
      if (typeof window === "undefined") return
      const titled = nextTurns.length
        ? nextWindows.map((w) =>
            w.id === nextSession ? { ...w, title: titleFromTurns(nextTurns), updatedAt: Date.now() } : w
          )
        : nextWindows
      const turnsById: Record<string, Turn[]> = {}
      try {
        const prev = loadLocalStore(tenantId, userId)
        Object.assign(turnsById, prev.turnsById)
      } catch {
        // ignore
      }
      turnsById[nextSession] = nextTurns
      localStorage.setItem(
        storageKey(tenantId, userId),
        JSON.stringify({ activeId: nextSession, windows: titled, turnsById })
      )
    },
    [tenantId, userId]
  )

  useEffect(() => {
    if (!hydrated || !authenticated) return
    const local = loadLocalStore(tenantId, userId)
    const active = local.activeId || newSessionId()
    setSessionId(active)
    setTurns(local.turnsById[active] || [])
    nextId.current = (local.turnsById[active] || []).reduce((m, t) => Math.max(m, t.id + 1), 0)
    setWindows(
      local.windows.length
        ? local.windows
        : [{ id: active, title: titleFromTurns(local.turnsById[active] || []), updatedAt: Date.now() }]
    )
    setReady(true)

    if (!token) return
    void (async () => {
      try {
        const remote = await listAssistantSessions(token)
        setWindows((prev) => {
          const byId = new Map<string, ChatWindow>()
          for (const row of remote) {
            byId.set(row.session_id, {
              id: row.session_id,
              title: row.title || "New chat",
              updatedAt: row.updated_at ? Date.parse(row.updated_at) : Date.now(),
            })
          }
          for (const w of prev) {
            if (!byId.has(w.id)) byId.set(w.id, w)
          }
          if (!byId.has(active)) {
            byId.set(active, {
              id: active,
              title: titleFromTurns(local.turnsById[active] || []),
              updatedAt: Date.now(),
            })
          }
          return [...byId.values()].sort((a, b) => b.updatedAt - a.updatedAt)
        })
      } catch {
        // local history still works if the list endpoint is not up yet
      }
    })()
  }, [authenticated, hydrated, tenantId, token, userId])

  useEffect(() => {
    if (!ready || !sessionId) return
    persist(sessionId, turns, windows)
  }, [persist, ready, sessionId, turns, windows])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "end",
    })
  }, [turns, reduce])

  const openWindow = useCallback(
    async (id: string) => {
      if (id === sessionRef.current) return
      abortRef.current?.abort()
      setActiveCite(null)
      setError(null)
      setSessionId(id)
      const local = loadLocalStore(tenantId, userId)
      let nextTurns = local.turnsById[id] || []
      if (token) {
        try {
          const detail = await getAssistantSession(token, id)
          if (detail.history?.length) {
            nextTurns = historyToTurns(detail.history)
          }
        } catch {
          // keep local copy
        }
      }
      setTurns(nextTurns)
      nextId.current = nextTurns.reduce((m, t) => Math.max(m, t.id + 1), 0)
    },
    [tenantId, token, userId]
  )

  const startNewChat = useCallback(() => {
    abortRef.current?.abort()
    const id = newSessionId()
    setActiveCite(null)
    setError(null)
    setSessionId(id)
    setTurns([])
    nextId.current = 0
    setWindows((prev) => [{ id, title: "New chat", updatedAt: Date.now() }, ...prev.filter((w) => w.id !== id)])
  }, [])

  useEffect(() => {
    if (!pending || !ready) return
    if (pending.type === "new") {
      startNewChat()
    } else if (pending.type === "open") {
      void openWindow(pending.id)
    }
    clearPending()
  }, [clearPending, openWindow, pending, ready, startNewChat])

  const ask = useCallback(
    async (text: string) => {
      if (!token || !authenticated) {
        setError("Sign in to chat against the live assistant.")
        return
      }
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setError(null)
      setActiveCite(null)
      setSourcesOpen(true)
      const userTurnId = nextId.current++
      const answerId = nextId.current++
      setTurns((prev) => [
        ...prev,
        { kind: "user", id: userTurnId, text },
        { kind: "answer", id: answerId, text: "", sources: [], settled: false },
      ])
      setWindows((prev) => {
        const exists = prev.some((w) => w.id === sessionRef.current)
        const title = text.slice(0, 80)
        const row = { id: sessionRef.current, title, updatedAt: Date.now() }
        return exists
          ? [row, ...prev.filter((w) => w.id !== sessionRef.current)]
          : [row, ...prev]
      })

      try {
        await streamAssistantChat({
          token,
          prompt: text,
          sessionId: sessionRef.current,
          tenantId: claims?.tenant_id,
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === "token") {
              setTurns((prev) =>
                prev.map((t) =>
                  t.kind === "answer" && t.id === answerId
                    ? { ...t, text: stripInlineCitations(t.text + event.text) }
                    : t
                )
              )
            }
            if (event.type === "final") {
              const providerError = event.generation_error
              setTurns((prev) =>
                prev.map((t) =>
                  t.kind === "answer" && t.id === answerId
                    ? {
                        ...t,
                        text: providerError
                          ? ""
                          : stripInlineCitations(event.response_text || t.text),
                        sources: citationsToSources(event.citations || []),
                        error: providerError
                          ? event.response_text ||
                            "The language model did not return a usable answer."
                          : undefined,
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
              ? {
                  ...t,
                  error: t.error || "Incomplete assistant response.",
                  settled: true,
                }
              : t
          )
        )
      } catch (err) {
        const aborted =
          (err instanceof DOMException && err.name === "AbortError") ||
          (err instanceof Error && err.name === "AbortError") ||
          controller.signal.aborted
        if (aborted) {
          setTurns((prev) =>
            prev.map((t) =>
              t.kind === "answer" && t.id === answerId && !t.settled
                ? {
                    ...t,
                    text: t.text || "Stopped.",
                    settled: true,
                  }
                : t
            )
          )
          return
        }
        const message =
          err instanceof ApiError
            ? err.message
            : err instanceof DOMException && err.name === "TimeoutError"
              ? "Chat timed out waiting for the model. Retrieval and Qwen can take more than a few seconds — retry once."
              : "Chat request failed."
        setTurns((prev) =>
          prev.map((t) =>
            t.kind === "answer" && t.id === answerId
              ? { ...t, error: message, settled: true }
              : t
          )
        )
      } finally {
        if (abortRef.current === controller) abortRef.current = null
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
  const sessionTitle =
    windows.find((w) => w.id === sessionId)?.title?.trim() || "New chat"

  if (!hydrated) {
    return <div className="flex h-full min-h-0" />
  }

  if (!authenticated) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-lg font-medium tracking-[-0.01em] text-neutral-800">
          Sign in to chat
        </p>
        <p className="max-w-md text-[0.9375rem] leading-relaxed text-neutral-500">
          Your conversations are saved per account so you can reopen earlier
          windows.
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
        {!empty && (
          <header className="shrink-0 border-b border-border-subtle/70 px-6 py-3">
            <h1 className="mx-auto max-w-3xl truncate text-center text-[0.8125rem] font-medium tracking-[-0.01em] text-neutral-500">
              {sessionTitle}
            </h1>
          </header>
        )}

        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 sm:px-8">
          {empty ? (
            <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 pt-[18vh] text-center">
              <h2 className="font-heading text-[clamp(1.75rem,3.2vw,2.25rem)] font-normal tracking-[-0.03em] text-neutral-800">
                What do you want to know?
              </h2>
              <p className="max-w-md text-[1rem] leading-[1.65] text-neutral-500">
                Ask in plain language. Answers come from your indexed documents,
                with sources in the right-hand rail.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-9 py-8 pb-12">
              {turns.map((turn) =>
                turn.kind === "user" ? (
                  <motion.div
                    key={turn.id}
                    initial={reduce ? false : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, ease: EASE_OUT }}
                    className="flex justify-end"
                  >
                    <div className="max-w-[min(85%,36rem)] rounded-[1.35rem] bg-neutral-100 px-4 py-2.5 text-[0.9875rem] leading-[1.55] tracking-[-0.011em] text-neutral-800">
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

        <div className="shrink-0 px-4 pb-4 pt-2 sm:px-8 sm:pb-5">
          <div className="mx-auto max-w-3xl">
            <Composer onSend={ask} onStop={stopGeneration} busy={busy} disabled={busy} />
            {error ? (
              <p role="alert" className="mt-2 text-center text-xs text-destructive">
                {error}
              </p>
            ) : (
              <p className="mt-2.5 text-center text-[0.6875rem] leading-snug text-neutral-400">
                SynQ can make mistakes. Check important answers against your sources.
              </p>
            )}
          </div>
        </div>
      </div>

      <aside
        className={cn(
          "hidden shrink-0 border-l border-border-subtle transition-[width] duration-200 xl:block",
          sourcesOpen ? "w-80" : "w-12"
        )}
      >
        <div className="flex items-center justify-between gap-2 px-3 py-4">
          {sourcesOpen ? (
            <span className="text-xs font-medium text-muted-foreground">
              Sources · {railSources.length}
            </span>
          ) : (
            <span className="sr-only">Sources</span>
          )}
          <button
            type="button"
            onClick={() => setSourcesOpen((open) => !open)}
            aria-expanded={sourcesOpen}
            aria-label={sourcesOpen ? "Minimize sources" : "Expand sources"}
            className="grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {sourcesOpen ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
          </button>
        </div>
        {sourcesOpen ? (
          railSources.length === 0 ? (
            <p className="px-4 text-sm text-muted-foreground">
              Records used for the latest answer show up here.
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
          )
        ) : null}
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
  const [sourcesMinimized, setSourcesMinimized] = useState(false)

  return (
    <div className="flex w-full min-w-0 flex-col gap-4">
      <AnimatePresence>
        {!turn.settled && !turn.text && !turn.error && (
          <motion.p
            key="retrieving"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="flex items-center gap-2.5 text-[0.9875rem] leading-relaxed text-neutral-500"
          >
            <Loader size={16} />
            Searching connected sources…
          </motion.p>
        )}
      </AnimatePresence>

      {turn.error && (
        <p role="alert" className="text-[0.9375rem] leading-relaxed text-destructive">
          {turn.error}
        </p>
      )}

      {turn.sources.length > 0 && turn.settled && (
        <div className="xl:hidden">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Sources · {turn.sources.length}
            </span>
            <button
              type="button"
              onClick={() => setSourcesMinimized((v) => !v)}
              aria-expanded={!sourcesMinimized}
              className="text-xs text-muted-foreground underline-offset-2 hover:underline"
            >
              {sourcesMinimized ? "Show" : "Minimize"}
            </button>
          </div>
          {!sourcesMinimized && (
            <ul className="flex flex-col gap-2">
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
      )}

      {turn.text && (
        <div className="min-w-0 wrap-break-word whitespace-pre-wrap text-[1.0625rem] leading-[1.75] tracking-[-0.014em] text-neutral-800">
          {turn.text}
          {streaming && (
            <motion.span
              aria-hidden
              animate={{ opacity: [1, 0.25, 1] }}
              transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut" }}
              className="ml-0.5 inline-block h-[1.05em] w-0.5 translate-y-[0.18em] rounded-full bg-ink-blue"
            />
          )}
        </div>
      )}
    </div>
  )
}
