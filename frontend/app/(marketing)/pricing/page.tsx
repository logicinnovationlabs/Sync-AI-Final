import type { Metadata } from "next"
import { PricingTable } from "@/components/landing/pricing-table"
import { FaqSection } from "@/components/landing/faq-section"

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "What SynQ costs, what's in each plan, and which sources each one reads.",
}

export default function PricingPage() {
  return (
    <>
      <section className="relative">
        <div className="mx-auto max-w-6xl px-6 pt-20 pb-20 lg:pt-28">
          <div className="mx-auto mb-14 flex max-w-2xl flex-col items-center gap-5 text-center">
            <p className="text-[0.875rem] font-medium text-ink-blue">Pricing</p>
            <h1 className="font-heading text-[clamp(2.25rem,5vw,3.5rem)] leading-[1.08] font-normal tracking-[-0.02em] text-balance">
              One price per workspace
            </h1>
            <p className="max-w-[52ch] text-[1.0625rem] leading-relaxed text-muted-foreground text-pretty">
              Every plan answers unlimited questions and cites every claim. What
              changes is how many people you bring and how many of your systems
              SynQ reads.
            </p>
          </div>

          <PricingTable />
        </div>
      </section>

      <FaqSection />
    </>
  )
}
