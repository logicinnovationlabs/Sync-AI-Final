"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { CiteMark } from "@/components/landing/cite-mark"
import { Composer } from "@/components/chat/composer"
import { SourceCard } from "@/components/chat/source-card"
import { Loader } from "@/components/motion/loader"
import { DEMO_ANSWERS, type DemoAnswer, type Token } from "@/lib/demo-answers"
import { EASE_OUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * The chat surface.
 *
 * ── Why this runs on scripted data ───────────────────────────────────────────
 * The backend has no chat, search or documents endpoint — `app/main.py` mounts
 * auth, oauth, me, admin, connectors and webhooks, and nothing else. So this
 * drives off `DEMO_ANSWERS`: the *same* scripted material as the landing page.
 * The product can't promise something the marketing page doesn't, and when the
 * real endpoint lands the only thing to replace is `answerFor`.
 *
 * Anything outside that set is told plainly that it can't be answered yet.
 *
 * ── Why the streaming was rebuilt ────────────────────────────────────────────
 * The first version revealed `DEMO_ANSWERS`' tokens directly, one per 190ms.
 * But those tokens are *clause*-sized — split at citation boundaries, not at
 * words — so the answer arrived in six lurching chunks, each fading through a
 * 4px blur over 340ms. Chunks overlapped their own fades and it read as a
 * slideshow, not as typing.
 *
 * Now the clauses are atomised to words (`atomize`) and revealed a few at a
 * time on a ~55ms tick, with a 140ms opacity fade and no filter. Citations stay
 * atomic so a mark never splits.
 *
 * The reveal counter lives inside `AnswerTurn`, not in the parent's turn array.
 * Ticking it in the parent re-rendered every message in the transcript ~20
 * times a second, which is what made a long conversation stutter.
 */

/** What we say when the question isn't in the scripted set. */
const UNSCRIPTED: Token[] = [
  { text: "I can't answer that one yet. This build has no chat backend — " },
  { text: "no search or documents endpoint exists on the API", strong: true },
  {
    text: ", so answers come from a small scripted set while that gets built. Pick one of the suggested questions to see how citations actually behave.",
  },
]

type Turn =
  | { kind: "user"; id: number; text: string }
  | { kind: "answer"; id: number; demoId: string | null; settled: boolean }

function answerFor(text: string): DemoAnswer | null {
  const q = text.trim().toLowerCase()
  return (
    DEMO_ANSWERS.find(
      (d) =>
        d.question.toLowerCase() === q ||
        d.label.toLowerCase() === q ||
        // Loose match so a paraphrase of a suggested question still lands
        // rather than falling through to the "can't answer" path.
        d.label
          .toLowerCase()
          .split(" ")
          .filter((w) => w.length > 4)
          .some((w) => q.includes(w))
    ) ?? null
  )
}

function tokensFor(demoId: string | null): Token[] {
  if (!demoId) return UNSCRIPTED
  return DEMO_ANSWERS.find((d) => d.id === demoId)?.answer ?? UNSCRIPTED
}

function sourcesFor(demoId: string | null) {
  if (!demoId) return []
  return DEMO_ANSWERS.find((d) => d.id === demoId)?.sources ?? []
}

type Atom = { word: string; strong?: boolean } | { cite: number }

/**
 * Clause-sized tokens → word-sized atoms, each keeping the whitespace around
 * it so the reassembled paragraph is byte-identical to the original.
 */
function atomize(tokens: Token[]): Atom[] {
  const atoms: Atom[] = []
  for (const token of tokens) {
    if (token.cite !== undefined) {
      atoms.push({ cite: token.cite })
      continue
    }
    for (const word of token.text.match(/\s*\S+\s*/g) ?? []) {
      atoms.push({ word, strong: token.strong })
    }
  }
  return atoms
}

// Retrieval is short now. It used to run 460ms + 360ms per source — over a
// second and a half of nothing before a word appeared.
const RETRIEVE_BASE_MS = 240
const RETRIEVE_PER_SOURCE_MS = 90
/** Reveal cadence. Words per tick keeps React renders well under the tick rate. */
const STREAM_TICK_MS = 55
const WORDS_PER_TICK = 2

export function ChatView() {
  const reduce = useReducedMotion()
  const [turns, setTurns] = useState<Turn[]>([])
  const [activeCite, setActiveCite] = useState<number | null>(null)
  const nextId = useRef(0)
  const bottomRef = useRef<HTMLDivElement>(null)

  const last = turns[turns.length - 1]
  const busy = last?.kind === "answer" && !last.settled

  const settle = useCallback((id: number) => {
    setTurns((prev) =>
      prev.map((t) => (t.kind === "answer" && t.id === id ? { ...t, settled: true } : t))
    )
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "end",
    })
  }, [turns.length, reduce])

  function ask(text: string) {
    const demo = answerFor(text)
    setActiveCite(null)
    setTurns((prev) => [
      ...prev,
      { kind: "user", id: nextId.current++, text },
      { kind: "answer", id: nextId.current++, demoId: demo?.id ?? null, settled: false },
    ])
  }

  // The rail mirrors the most recent answer that actually retrieved something,
  // so it doesn't blank out when an unscripted question follows a good one.
  const railTurn = [...turns]
    .reverse()
    .find(
      (t): t is Extract<Turn, { kind: "answer" }> =>
        t.kind === "answer" && sourcesFor(t.demoId).length > 0
    )
  const railSources = railTurn ? sourcesFor(railTurn.demoId) : []

  const empty = turns.length === 0

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-6 py-8">
            {empty ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-8 text-center">
                <div className="flex flex-col gap-3">
                  <h1 className="font-heading text-[clamp(1.75rem,3.5vw,2.5rem)] leading-[1.15] font-normal tracking-[-0.02em]">
                    What do you want to know?
                  </h1>
                  <p className="max-w-[46ch] text-sm leading-relaxed text-muted-foreground">
                    Every answer comes back with the ledger entry, message or
                    file it came from.
                  </p>
                </div>
                <Suggestions onPick={ask} />
              </div>
            ) : (
              <div className="flex flex-col gap-8">
                {turns.map((turn) =>
                  turn.kind === "user" ? (
                    <motion.div
                      key={turn.id}
                      initial={reduce ? false : { opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, ease: EASE_OUT }}
                      className="flex justify-end"
                    >
                      <p className="max-w-[85%] rounded-[1.25rem] rounded-br-md bg-secondary px-4 py-2.5 text-[0.9375rem] leading-relaxed">
                        {turn.text}
                      </p>
                    </motion.div>
                  ) : (
                    <AnswerTurn
                      key={turn.id}
                      id={turn.id}
                      demoId={turn.demoId}
                      settled={turn.settled}
                      onSettled={settle}
                      activeCite={activeCite}
                      setActiveCite={setActiveCite}
                      reduce={Boolean(reduce)}
                    />
                  )
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="shrink-0 border-t border-border-subtle bg-background/80 backdrop-blur-sm">
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-6 py-4">
            {!empty && <Suggestions onPick={ask} compact />}
            <Composer onSend={ask} disabled={busy} />
            <p className="text-center text-[0.6875rem] text-muted-foreground">
              Scripted demo data — the chat backend isn&apos;t built yet.
            </p>
          </div>
        </div>
      </div>

      {/* Sources rail. Below xl the same cards render inline under the answer,
          which beats a drawer for something you want to read alongside. */}
      <aside className="hidden w-80 shrink-0 flex-col overflow-y-auto border-l border-border-subtle px-5 py-8 xl:flex">
        <p className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
          Sources · {railSources.length}
        </p>
        {railSources.length === 0 ? (
          <p className="mt-4 text-[0.8125rem] leading-relaxed text-muted-foreground">
            Records cited in an answer show up here.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-2.5">
            <AnimatePresence mode="popLayout">
              {railSources.map((source, i) => (
                <motion.li
                  key={`${railTurn?.id}-${source.n}`}
                  layout={!reduce}
                  initial={reduce ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: 0.2,
                    ease: EASE_OUT,
                    delay: reduce ? 0 : i * 0.04,
                  }}
                >
                  <SourceCard
                    source={source}
                    active={activeCite === source.n}
                    onActivate={setActiveCite}
                    onDeactivate={() => setActiveCite(null)}
                  />
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </aside>
    </div>
  )
}

function Suggestions({
  onPick,
  compact = false,
}: {
  onPick: (text: string) => void
  compact?: boolean
}) {
  const reduce = useReducedMotion()

  return (
    <div
      role="group"
      aria-label="Suggested questions"
      className={cn(
        "flex flex-wrap gap-2",
        compact ? "justify-start" : "justify-center"
      )}
    >
      {DEMO_ANSWERS.map((d, i) => (
        <motion.button
          key={d.id}
          type="button"
          onClick={() => onPick(d.question)}
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.2,
            ease: EASE_OUT,
            delay: reduce ? 0 : i * 0.04,
          }}
          whileTap={reduce ? undefined : { scale: 0.97 }}
          className={cn(
            "cursor-pointer rounded-full border border-border-subtle text-muted-foreground transition-colors duration-150 outline-none hover:border-border hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            compact ? "px-3 py-1 text-[0.75rem]" : "px-4 py-2 text-[0.875rem]"
          )}
        >
          {d.label}
        </motion.button>
      ))}
    </div>
  )
}

function AnswerTurn({
  id,
  demoId,
  settled,
  onSettled,
  activeCite,
  setActiveCite,
  reduce,
}: {
  id: number
  demoId: string | null
  settled: boolean
  onSettled: (id: number) => void
  activeCite: number | null
  setActiveCite: (n: number | null) => void
  reduce: boolean
}) {
  const atoms = useMemo(() => atomize(tokensFor(demoId)), [demoId])
  const sources = useMemo(() => sourcesFor(demoId), [demoId])

  // Reduced motion and an already-settled turn both mean "show the finished
  // answer". Derived into the initial state rather than corrected by an effect
  // — mirroring `useReducedMotion()` into state with setState is the exact
  // pattern `react-hooks/set-state-in-effect` exists to catch (SUMMARY.md §5).
  const instant = settled || reduce

  // `revealed` lives here so ticking it re-renders one message, not the
  // whole transcript.
  const [revealed, setRevealed] = useState(instant ? atoms.length : 0)
  const [retrieving, setRetrieving] = useState(!instant)

  useEffect(() => {
    if (instant) return
    const delay = RETRIEVE_BASE_MS + RETRIEVE_PER_SOURCE_MS * sources.length
    const timer = setTimeout(() => setRetrieving(false), delay)
    return () => clearTimeout(timer)
    // Runs once per turn — `settled` flips exactly once, at the end.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (retrieving || settled || revealed >= atoms.length) return
    const timer = setTimeout(() => {
      setRevealed((n) => Math.min(n + WORDS_PER_TICK, atoms.length))
    }, STREAM_TICK_MS)
    return () => clearTimeout(timer)
  }, [retrieving, settled, revealed, atoms.length])

  useEffect(() => {
    if (!settled && !retrieving && revealed >= atoms.length) onSettled(id)
  }, [settled, retrieving, revealed, atoms.length, id, onSettled])

  const streaming = !settled && !retrieving && revealed < atoms.length

  return (
    <div className="flex flex-col gap-4">
      {/* Not `mode="wait"` — waiting for the loader to leave before the text
          could enter put a dead beat exactly where the user is looking.
          `popLayout` instead, so the departing loader is pulled out of flow and
          the first line of the answer doesn't get shoved down by a row that is
          already on its way out. */}
      <AnimatePresence initial={false} mode="popLayout">
        {retrieving && (
          <motion.p
            key="retrieving"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="flex items-center gap-2.5 text-[0.9375rem] text-muted-foreground"
          >
            <Loader variant="dots" size={16} label="Searching sources" />
            Searching connected sources…
          </motion.p>
        )}
      </AnimatePresence>

      {!retrieving && (
        <p className="max-w-[62ch] text-[1.0625rem] leading-[1.85] text-foreground">
          {atoms.slice(0, revealed).map((atom, i) =>
            "cite" in atom ? (
              <CiteMark
                key={i}
                n={atom.cite}
                active={activeCite === atom.cite}
                onActivate={setActiveCite}
                onDeactivate={() => setActiveCite(null)}
              />
            ) : (
              <motion.span
                key={i}
                initial={reduce || settled ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.14, ease: EASE_OUT }}
                className={atom.strong ? "font-medium" : undefined}
              >
                {atom.word}
              </motion.span>
            )
          )}
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

      {/* Inline sources — the rail's counterpart below xl. */}
      {sources.length > 0 && !retrieving && (
        <ul className="flex flex-col gap-2.5 xl:hidden">
          {sources.map((source, i) => (
            <motion.li
              key={source.n}
              initial={reduce || settled ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.2,
                ease: EASE_OUT,
                delay: reduce ? 0 : i * 0.04,
              }}
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
