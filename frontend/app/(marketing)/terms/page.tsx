import type { Metadata } from "next"
import { LegalPage, LegalPlaceholder } from "@/components/landing/legal-page"

export const metadata: Metadata = {
  title: "Terms",
  robots: { index: false },
}

export default function TermsPage() {
  return (
    <LegalPage title="Terms">
      <LegalPlaceholder document="terms of service" />
    </LegalPage>
  )
}
