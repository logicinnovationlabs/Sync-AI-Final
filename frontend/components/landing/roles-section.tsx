import { ScrollReveal } from "@/components/motion/scroll-reveal"
import { ConnectorLogo } from "@/components/connector-logo"
import { SectionHead, SectionShell } from "@/components/landing/section"
import { CONNECTORS } from "@/lib/connectors"
import { DEMO_ANSWERS, sourcesUsed } from "@/lib/demo-answers"

/**
 * Who actually asks these questions.
 *
 * Driven off DEMO_ANSWERS rather than its own copy, so the three people here
 * and the three questions in the demo are the same three questions by
 * construction — there is no second list to drift out of sync.
 */

const nameOf = (source: string) =>
  CONNECTORS.find((c) => c.source === source)?.shortLabel ?? source

export function RolesSection() {
  return (
    <SectionShell id="who">
      <SectionHead
        eyebrow="Who it's for"
        heading="Three people, three questions, one index"
        lead="The questions below aren't illustrative — they're the ones running in the demo above."
      />

      <div className="mt-12 grid gap-5 lg:grid-cols-3">
        {DEMO_ANSWERS.map((d, i) => (
          <ScrollReveal key={d.id} delay={i * 0.06} y={16}>
            <div className="group flex h-full flex-col gap-5 rounded-[1.5rem] border border-border-subtle bg-card p-8 transition-shadow duration-300 hover:shadow-[0_10px_44px_-14px_oklch(0.3_0.04_275/0.22)]">
              <p className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-ink-blue">
                {d.role}
              </p>

              <p className="font-heading text-[1.375rem] leading-[1.35] font-normal tracking-[-0.01em] text-balance">
                &ldquo;{d.question}&rdquo;
              </p>

              <p className="text-[0.9375rem] leading-relaxed text-muted-foreground">
                {d.roleNote}
              </p>

              {/* The sources that answer it, straight off the citations. */}
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-2">
                {sourcesUsed(d).map((s) => (
                  <span
                    key={s}
                    className="flex items-center gap-1.5 rounded-full border border-border-subtle px-2.5 py-1 text-[0.75rem] text-muted-foreground"
                  >
                    <ConnectorLogo source={s} bare className="size-3.5" />
                    {nameOf(s)}
                  </span>
                ))}
              </div>
            </div>
          </ScrollReveal>
        ))}
      </div>
    </SectionShell>
  )
}
