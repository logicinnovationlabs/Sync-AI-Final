"use client"

import { useEffect, useRef, useState } from "react"
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useInView,
  useReducedMotion,
} from "motion/react"
import { CiteMark } from "@/components/landing/cite-mark"
import { SectionHead, SectionShell } from "@/components/landing/section"
import { ConnectorLogo } from "@/components/connector-logo"
import { CONNECTORS, type ConnectorSourceType } from "@/lib/connectors"
import { DEMO_ANSWERS } from "@/lib/demo-answers"
import { EASE_OUT, SPRING_LAYOUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * The whole product in one gesture.
 *
 * Four systems, each holding a fragment of the same story, collapse into a
 * single cited answer. It is deliberately a *different kind* of thing from the
 * demo below: this poses the problem and shows the transformation, the demo
 * shows the detail of a real answer.
 *
 * The morph is motion's shared layout: each pane carries a stable `layoutId`,
 * and there are two render trees — a grid and the inside of the answer card —
 * that use the same ids. Motion tweens the boxes between them.
 *
 * The one thing that has to be right: the *contents* of each pane crossfade
 * while the *box* travels. Animating a box from 300×140 to 90×32 with live text
 * inside squashes the type mid-flight, which is the classic shared-layout
 * failure. So the pane's detail is wrapped in its own opacity layer that is
 * gone before the box finishes moving.
 */

type Fragment = {
  source: ConnectorSourceType
  n: number
  kind: string
  title: string
  body: string
  meta: string
}

// The same story DEMO_ANSWERS[0] tells, split back across the systems it came
// from — so the star and the demo can never disagree.
const FRAGMENTS: Fragment[] = [
  {
    source: "tally",
    n: 1,
    kind: "Voucher",
    title: "#TV-2026-0481",
    body: "Meridian Traders · Sundry Debtors",
    meta: "₹2,84,500 Dr",
  },
  {
    source: "whatsapp",
    n: 2,
    kind: "Message",
    title: "Meridian Traders",
    body: "“payment released on the 12th, please check”",
    meta: "12 Mar",
  },
  {
    source: "outlook",
    n: 3,
    kind: "Mail",
    title: "Re: March dues",
    body: "“sharing the remittance advice shortly”",
    meta: "14 Mar",
  },
  {
    source: "google_personal",
    n: 4,
    kind: "File",
    title: "INV-2026-0334.pdf",
    body: "Net 30 · due 04 Mar",
    meta: "₹1,12,000",
  },
]

const QUESTION = DEMO_ANSWERS[0].question

const ANSWER: { text?: string; cite?: number; strong?: boolean }[] = [
  { text: "Not yet — " },
  { text: "₹2,84,500 ", strong: true },
  { text: "is still outstanding across three invoices" },
  { cite: 1 },
  { cite: 4 },
  { text: ". They said payment went out on 12 March" },
  { cite: 2 },
  { text: " and promised a remittance advice" },
  { cite: 3 },
  { text: ", but nothing has posted against the ledger." },
]

// Long enough apart to read the four fragments, long enough together to read
// the answer and notice the citations.
const HOLD_APART_MS = 2600
const HOLD_TOGETHER_MS = 6200

const labelOf = (s: ConnectorSourceType) =>
  CONNECTORS.find((c) => c.source === s)?.shortLabel ?? s

export function Convergence() {
  const ref = useRef<HTMLDivElement>(null)
  // Not `once` — the loop should stop when the section scrolls away rather than
  // animating to an empty room.
  const inView = useInView(ref, { amount: 0.3 })
  const reduce = useReducedMotion()

  // Which citation is lit, shared between the answer marks and the source
  // chips — same bidirectional sync as the demo section below.
  const [activeCite, setActiveCite] = useState<number | null>(null)

  // Runs on a loop: apart, converge, hold, come apart, repeat. No button — you
  // arrive and it is already telling you the story.
  const [together, setTogether] = useState(false)
  const shown = reduce ? true : together

  useEffect(() => {
    if (reduce || !inView) return
    // Holding a source chip pauses the loop. Yanking the layout out from under
    // someone who is mid-hover is the fastest way to make a nice thing annoying.
    if (activeCite !== null) return
    const t = setTimeout(() => {
      setActiveCite(null)
      setTogether((v) => !v)
    }, together ? HOLD_TOGETHER_MS : HOLD_APART_MS)
    return () => clearTimeout(t)
  }, [together, inView, reduce, activeCite])

  return (
    <SectionShell id="converge">
      <SectionHead
        eyebrow="The idea"
        heading="Four systems hold one answer between them"
        lead="Nobody keeps the whole story in one place. The ledger has the number, the chat has the promise, the inbox has the excuse, the drive has the invoice."
      />

      <div ref={ref} className="mx-auto mt-12 max-w-5xl">
        <p className="mb-8 text-center font-heading text-[clamp(1.25rem,2.4vw,1.625rem)] leading-[1.35] font-normal tracking-[-0.01em] text-balance">
          &ldquo;{QUESTION}&rdquo;
        </p>

        <LayoutGroup id="converge">
          {!shown ? (
            /* ── APART ─────────────────────────────────────────────── */
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
              {FRAGMENTS.map((f, i) => (
                <motion.div
                  key={f.source}
                  layoutId={`frag-${f.source}`}
                  transition={SPRING_LAYOUT}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex flex-col gap-2.5 rounded-[1.25rem] border border-border-subtle bg-card p-4 shadow-[0_2px_24px_-10px_oklch(0.3_0.04_275/0.14)]"
                >
                  <motion.div layout="position" className="flex items-center gap-2">
                    <ConnectorLogo source={f.source} bare className="size-4" />
                    <span className="font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground">
                      {f.kind}
                    </span>
                  </motion.div>
                  {/* Detail lives in its own fading layer — see the note up top. */}
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2, delay: i * 0.04 }}
                    className="flex flex-col gap-1.5"
                  >
                    <p className="truncate text-[0.8125rem] font-medium">
                      {f.title}
                    </p>
                    <p className="line-clamp-2 text-[0.75rem] leading-relaxed text-muted-foreground">
                      {f.body}
                    </p>
                    <p className="font-mono text-[0.625rem] text-muted-foreground">
                      {f.meta}
                    </p>
                  </motion.div>
                </motion.div>
              ))}
            </div>
          ) : (
            /* ── TOGETHER ──────────────────────────────────────────── */
            <motion.div
              layout
              transition={SPRING_LAYOUT}
              className="mx-auto max-w-3xl rounded-[1.75rem] border border-border-subtle bg-card p-7 shadow-[0_10px_50px_-16px_oklch(0.3_0.04_275/0.22)] sm:p-9"
            >
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4, delay: 0.25, ease: EASE_OUT }}
                className="text-[1.0625rem] leading-[1.85] text-foreground"
              >
                {ANSWER.map((t, i) =>
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
                      transition={{
                        duration: 0.4,
                        delay: 0.3 + i * 0.05,
                        ease: EASE_OUT,
                      }}
                      className={t.strong ? "font-medium" : undefined}
                    >
                      {t.text}
                    </motion.span>
                  )
                )}
              </motion.p>

              {/* The four panes, arrived — now the answer's source chips.
                  Hovering one lights its citation in the sentence above, and
                  hovering a citation lights the chip. Real buttons so it works
                  by keyboard and by touch, not only under a pointer. */}
              <div className="mt-7 flex flex-wrap gap-2 border-t border-border-subtle pt-6">
                {FRAGMENTS.map((f) => {
                  const on = activeCite === f.n
                  return (
                    <motion.button
                      key={f.source}
                      type="button"
                      layoutId={`frag-${f.source}`}
                      transition={SPRING_LAYOUT}
                      onMouseEnter={() => setActiveCite(f.n)}
                      onMouseLeave={() => setActiveCite(null)}
                      onFocus={() => setActiveCite(f.n)}
                      onBlur={() => setActiveCite(null)}
                      aria-label={`Source ${f.n}: ${f.title}`}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 outline-none transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                        on
                          ? "border-ink-blue/45 bg-ink-blue/8"
                          : "border-border-subtle bg-surface hover:border-border"
                      )}
                    >
                      <motion.span layout="position" className="flex items-center gap-2">
                        <span
                          className={cn(
                            "flex size-[1.0625rem] shrink-0 items-center justify-center rounded-[4px] font-mono text-[0.625rem] font-semibold transition-colors duration-200",
                            on
                              ? "bg-ink-blue text-background"
                              : "bg-ink-blue/12 text-ink-blue"
                          )}
                        >
                          {f.n}
                        </span>
                        <ConnectorLogo source={f.source} bare className="size-4" />
                        <span className="text-[0.8125rem]">
                          {labelOf(f.source)}
                        </span>
                      </motion.span>
                    </motion.button>
                  )
                })}
              </div>

              {/* What that source actually said, revealed on hover. */}
              <AnimatePresence mode="wait">
                {activeCite !== null && (
                  <motion.div
                    key={activeCite}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.22, ease: EASE_OUT }}
                    className="mt-4 rounded-2xl bg-surface px-4 py-3"
                  >
                    {(() => {
                      const f = FRAGMENTS.find((x) => x.n === activeCite)
                      if (!f) return null
                      return (
                        <>
                          <p className="text-[0.8125rem] font-medium">
                            {f.title}
                          </p>
                          <p className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
                            {f.body}
                          </p>
                          <p className="mt-1 font-mono text-[0.6875rem] text-muted-foreground">
                            {labelOf(f.source)} · {f.meta}
                          </p>
                        </>
                      )
                    })()}
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </LayoutGroup>


      </div>
    </SectionShell>
  )
}
