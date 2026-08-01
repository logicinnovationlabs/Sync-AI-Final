import { ScrollReveal } from "@/components/motion/scroll-reveal"
import { TiltCard } from "@/components/motion/tilt-card"
import { SectionHead, SectionShell } from "@/components/landing/section"

/**
 * No icons. A building glyph for "tenant", a padlock for "security" and a key
 * for "keys" is the exact visual vocabulary of a generated landing page — it
 * decorates without adding information. The numbering carries the structure.
 */
const points = [
  {
    title: "Isolated per tenant",
    description:
      "Every business gets its own scoped database. All data, search and AI configuration are keyed by tenant — nothing is shared across them.",
  },
  {
    title: "Role boundaries, visible",
    description:
      "Admins manage connectors and users. Members get chat and documents. The boundary is structural, not a settings toggle.",
  },
  {
    title: "Ledgers stay on-prem",
    description:
      "Tally data is pushed by a signed agent running at your site over a long-lived token — not uploaded wholesale to a cloud connector.",
  },
  {
    title: "Every claim is traceable",
    description:
      "Answers are assembled from retrieved records and each one carries the voucher, message or file it came from. Nothing is asserted that can't be opened.",
  },
]

export function TrustSection() {
  return (
    <SectionShell id="security">
      <SectionHead
        eyebrow="Security"
        heading="Built with tenant isolation from day one"
        lead="Multi-tenancy that shows up in the product, not just in the schema."
      />

      <div className="mt-12 grid gap-5 sm:grid-cols-2">
        {points.map((point, i) => (
          <ScrollReveal key={point.title} delay={i * 0.05} y={16}>
            {/* beui TiltCard — spring-damped cursor tracking, so the cards
                acknowledge the pointer instead of sitting inert. */}
            <TiltCard
              max={5}
              className="h-full rounded-[1.5rem] border border-border-subtle bg-card transition-shadow duration-300 hover:shadow-[0_10px_44px_-14px_oklch(0.3_0.04_275/0.22)]"
            >
              <div className="flex h-full flex-col gap-3.5 p-8">
                <span className="font-mono text-[0.6875rem] text-ink-blue">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="text-[1.0625rem] font-medium">{point.title}</h3>
                <p className="text-[0.9375rem] leading-relaxed text-muted-foreground">
                  {point.description}
                </p>
              </div>
            </TiltCard>
          </ScrollReveal>
        ))}
      </div>
    </SectionShell>
  )
}
