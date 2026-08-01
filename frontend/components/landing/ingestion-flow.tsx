import { ScrollReveal } from "@/components/motion/scroll-reveal"
import { ConnectorLogo } from "@/components/connector-logo"
import { Panel, SectionHead, SectionShell } from "@/components/landing/section"
import { CONNECTORS } from "@/lib/connectors"

const steps = [
  {
    n: "01",
    title: "Connect once",
    body: "OAuth for Google and Microsoft, a webhook for WhatsApp Business, a signed agent for Tally. Then you're done touching it.",
  },
  {
    n: "02",
    title: "Indexing runs on its own",
    body: "Each source keeps its own schedule in the background — nothing to trigger, nothing to re-upload when a file changes.",
  },
  {
    n: "03",
    title: "Ask in plain language",
    body: "Answers stream back with a citation on every claim, pointing at the document, message or voucher it came from.",
  },
]

export function IngestionFlow() {
  return (
    <SectionShell id="how-it-works">
      <SectionHead
        eyebrow="How it works"
        heading="From four scattered systems to one cited answer"
        lead="Connect once. Everything after that happens without you."
      />

      <Panel className="mt-12 p-0 sm:p-0">
        {/* Sources entering, cadence on the right — the input side. */}
        <div className="grid divide-y divide-border-subtle sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
          {CONNECTORS.map((c, i) => (
            <ScrollReveal key={c.source} delay={i * 0.05} y={14}>
              <div className="flex flex-col gap-3 p-6">
                <ConnectorLogo source={c.source} bare className="size-5" />
                <p className="text-[0.9375rem] font-medium">{c.name}</p>
                <p className="font-mono text-[0.6875rem] text-muted-foreground">
                  {c.cadence}
                </p>
              </div>
            </ScrollReveal>
          ))}
        </div>

        <div className="border-t border-border-subtle bg-surface">
          <div className="grid gap-10 p-8 sm:p-12 lg:grid-cols-3">
            {steps.map((s, i) => (
              <ScrollReveal key={s.n} delay={i * 0.07} y={16}>
                <div className="flex flex-col gap-3">
                  <span className="font-mono text-[0.6875rem] text-ink-blue">
                    {s.n}
                  </span>
                  <h3 className="text-[1.0625rem] font-medium">{s.title}</h3>
                  <p className="text-[0.9375rem] leading-relaxed text-muted-foreground">
                    {s.body}
                  </p>
                </div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </Panel>
    </SectionShell>
  )
}
