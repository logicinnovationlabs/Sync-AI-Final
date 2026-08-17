import { Hero } from "@/components/landing/hero"
import { Convergence } from "@/components/landing/convergence"
import { DemoSection } from "@/components/landing/demo-section"
import { SourcesSection } from "@/components/landing/sources-section"
import { IngestionFlow } from "@/components/landing/ingestion-flow"
import { ComparisonSection } from "@/components/landing/comparison-section"
import { RolesSection } from "@/components/landing/roles-section"
import { TrustSection } from "@/components/landing/trust-section"
import { FaqSection } from "@/components/landing/faq-section"
import { FinalCta } from "@/components/landing/final-cta"

export default function MarketingHomePage() {
  return (
    <>
      <Hero />
      <Convergence />
      <DemoSection />
      <SourcesSection />
      <IngestionFlow />
      <ComparisonSection />
      <RolesSection />
      <TrustSection />
      <FaqSection />
      <FinalCta />
    </>
  )
}
