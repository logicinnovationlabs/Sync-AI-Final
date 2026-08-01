"use client"

import { useEffect, useReducer, useRef, useState } from "react"
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react"
import { Search } from "lucide-react"
import { CiteMark } from "@/components/landing/cite-mark"
import { SectionHead, SectionShell } from "@/components/landing/section"
import { ConnectorLogo } from "@/components/connector-logo"
import { DEMO_ANSWERS } from "@/lib/demo-answers"
import { EASE_OUT, SPRING_LAYOUT, SPRING_PRESS } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * The demo, rebuilt.
 *
 * It used to be an app window drawn on the page — a bordered box with a fake
 * "CHAT" toolbar, a connector chip strip the hero had already shown 400px
 * above, and a <span> styled to look like a composer that did nothing when you
 * clicked it. That is a different design language from the rest of this page,
 * which is white-on-white and typographic, and the dead composer was the
 * detail that cost it the most.
 *
 * Two changes:
 *
 *   1. The chrome is gone. The question is set in the display face, the answer
 *      is typeset at reading size on the page itself, and the sources sit in
 *      the margin as cards. Content, not a screenshot of content.
 *
 *   2. You choose the question. The old version played one scripted answer on
 *      an 8.2s loop you could only watch — the wrong affordance on a page whose
 *      whole pitch is asking. Three questions, three source mixes, and the
 *      first one plays itself once when you arrive so the section is never
 *      dead on landing.
 *
 * The answer↔source sync is the argument the section exists to make: hovering
 * or focusing a mark lights its source, and hovering or focusing a source
 * lights its mark. PRODUCT.md's first principle is never letting the
 * assistant's voice outrun what it can point back to; this is that, visible.
 */

/** phase: 0 idle → 1 retrieving → 2 streaming → 3 settled */
type State = { phase: number; tokens: number; sources: number }
const INITIAL: State = { phase: 0, tokens: 0, sources: 0 }

function makeReducer(tokenCount: number, sourceCount: number) {
  return function reducer(s: State, a: "tick" | "reset"): State {
    if (a === "reset") return INITIAL
    if (s.phase === 0) return { ...s, phase: 1 }
    if (s.phase === 1) {
      const sources = s.sources + 1
      return sources >= sourceCount
        ? { ...s, sources, phase: 2 }
        : { ...s, sources }
    }
    if (s.phase === 2) {
      const tokens = s.tokens + 1
      return tokens >= tokenCount ? { ...s, tokens, phase: 3 } : { ...s, tokens }
    }
    return s
  }
}

// Phase 3 has no timer — the answer rests. Selecting another question is what
// advances it now, not a clock.
const STEP_MS: Record<number, number> = { 0: 550, 1: 400, 2: 250 }

export function DemoSection() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { amount: 0.3, once: true })
  const reduce = useReducedMotion()

  const [selected, setSelected] = useState(DEMO_ANSWERS[0].id)
  const [activeCite, setActiveCite] = useState<number | null>(null)

  const demo = DEMO_ANSWERS.find((d) => d.id === selected) ?? DEMO_ANSWERS[0]

  const [state, dispatch] = useReducer(
    makeReducer(demo.answer.length, demo.sources.length),
    INITIAL
  )

  // `once: true` means inView latches on and stays on, so it is already the
  // "has started" flag — mirroring it into state would just be a second copy
  // of the same boolean, updated a render later.
  useEffect(() => {
    if (reduce || !inView || state.phase === 3) return
    const t = setTimeout(() => dispatch("tick"), STEP_MS[state.phase])
    return () => clearTimeout(t)
  }, [state, inView, reduce])

  function select(id: string) {
    setActiveCite(null)
    setSelected(id)
    dispatch("reset")
  }

  // Reduced motion resolves to the finished answer rather than a frozen
  // half-state; the pills still switch between them.
  const done = reduce || state.phase === 3
  const visibleTokens = done ? demo.answer.length : state.tokens
  const visibleSources = done ? demo.sources.length : state.sources
  const streaming = !done && state.phase === 2
  const retrieving = !done && state.phase <= 1

  return (
    <SectionShell id="demo">
      <SectionHead
        eyebrow="See it work"
        heading="One question, four systems, one cited answer"
        lead="Pick a question. The answer streams back with the ledger entry, the message and the file it came from — hover any citation to see exactly which."
      />

      <div ref={ref} className="mx-auto mt-12 max-w-5xl">
        {/* Question pills. Real buttons, one row, wrapping on narrow screens. */}
        {/* aria-pressed toggles rather than role="tab": a real tablist needs
            matching tabpanel roles and aria-controls wiring, and half-applied
            tab semantics are worse for a screen reader than none. */}
        <div
          role="group"
          aria-label="Example questions"
          className="flex flex-wrap justify-center gap-2"
        >
          {DEMO_ANSWERS.map((d) => {
            const on = d.id === selected
            return (
              <button
                key={d.id}
                type="button"
                aria-pressed={on}
                onClick={() => select(d.id)}
                className={cn(
                  "relative cursor-pointer rounded-full px-4 py-2 text-[0.875rem] transition-colors duration-200 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  on
                    ? "text-primary-foreground"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                )}
              >
                {on && (
                  <motion.span
                    layoutId="demo-pill"
                    transition={SPRING_LAYOUT}
                    className="absolute inset-0 -z-10 rounded-full bg-primary"
                  />
                )}
                {d.label}
              </button>
            )
          })}
        </div>

        <div className="mt-12 grid gap-10 lg:grid-cols-[1.6fr_1fr] lg:gap-14">
          {/* The conversation, as prose on the page. No frame. */}
          <div className="flex flex-col">
            <AnimatePresence mode="wait">
              <motion.p
                key={`${demo.id}-q`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.32, ease: EASE_OUT }}
                className="font-heading text-[clamp(1.375rem,2.6vw,1.75rem)] leading-[1.3] font-normal tracking-[-0.01em] text-balance"
              >
                {demo.question}
              </motion.p>
            </AnimatePresence>

            <div className="mt-6 min-h-[11rem]">
              <AnimatePresence mode="wait">
                {retrieving ? (
                  <motion.p
                    key="retrieving"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-center gap-2 text-[0.9375rem] text-muted-foreground"
                  >
                    <Search className="size-4 shrink-0" />
                    Searching connected sources…
                  </motion.p>
                ) : (
                  <motion.p
                    key={`${demo.id}-a`}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2 }}
                    className="max-w-[62ch] text-[1.0625rem] leading-[1.85] text-foreground"
                  >
                    {demo.answer.slice(0, visibleTokens).map((t, i) =>
                      t.cite !== undefined ? (
                        <CiteMark
                          key={i}
                          n={t.cite}
                          active={activeCite === t.cite}
                          onActivate={setActiveCite}
                          onDeactivate={() => setActiveCite(null)}
                        />
                      ) : (
                        <motion.span
                          key={i}
                          initial={{ opacity: 0, filter: "blur(4px)" }}
                          animate={{ opacity: 1, filter: "blur(0px)" }}
                          transition={{ duration: 0.34, ease: EASE_OUT }}
                          className={t.strong ? "font-medium" : undefined}
                        >
                          {t.text}
                        </motion.span>
                      )
                    )}
                    {streaming && (
                      <motion.span
                        aria-hidden
                        animate={{ opacity: [1, 0.15, 1] }}
                        transition={{ duration: 1, repeat: Infinity }}
                        className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[0.18em] rounded-full bg-ink-blue"
                      />
                    )}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Sources, floating in the margin. */}
          <div className="flex flex-col gap-3">
            <p className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
              Sources · {visibleSources}
            </p>

            <ul className="flex flex-col gap-2.5">
              <AnimatePresence mode="popLayout">
                {demo.sources.slice(0, visibleSources).map((s) => {
                  const on = activeCite === s.n
                  return (
                    <motion.li
                      key={`${demo.id}-${s.n}`}
                      layout
                      initial={{ opacity: 0, y: 10, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.97 }}
                      transition={{ duration: 0.36, ease: EASE_OUT }}
                    >
                      <motion.button
                        type="button"
                        onMouseEnter={() => setActiveCite(s.n)}
                        onMouseLeave={() => setActiveCite(null)}
                        onFocus={() => setActiveCite(s.n)}
                        onBlur={() => setActiveCite(null)}
                        animate={{ y: on ? -2 : 0 }}
                        transition={SPRING_PRESS}
                        className={cn(
                          "w-full cursor-pointer rounded-[1rem] border bg-card p-3.5 text-left transition-colors duration-200 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                          on
                            ? "border-ink-blue/45 shadow-[0_8px_28px_-12px_oklch(0.3_0.04_275/0.28)]"
                            : "border-border-subtle hover:border-border"
                        )}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "flex size-[1.0625rem] shrink-0 items-center justify-center rounded-[4px] font-mono text-[0.625rem] font-semibold transition-colors duration-200",
                              on
                                ? "bg-ink-blue text-background"
                                : "bg-ink-blue/12 text-ink-blue"
                            )}
                          >
                            {s.n}
                          </span>
                          <ConnectorLogo
                            source={s.source}
                            bare
                            className="size-3.5"
                          />
                          <span className="min-w-0 flex-1 truncate text-[0.8125rem] font-medium">
                            {s.title}
                          </span>
                        </div>
                        <p className="mt-1.5 line-clamp-2 text-[0.75rem] leading-relaxed text-muted-foreground">
                          {s.snippet}
                        </p>
                        <p className="mt-1.5 font-mono text-[0.625rem] text-muted-foreground">
                          {s.meta}
                        </p>
                      </motion.button>
                    </motion.li>
                  )
                })}
              </AnimatePresence>
            </ul>
          </div>
        </div>
      </div>
    </SectionShell>
  )
}
