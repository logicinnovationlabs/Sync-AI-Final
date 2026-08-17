import type { Metadata } from "next"
import { LegalPage, LegalPlaceholder } from "@/components/landing/legal-page"

export const metadata: Metadata = {
  title: "Privacy",
  robots: { index: false },
}

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy">
      <LegalPlaceholder document="privacy policy" />
    </LegalPage>
  )
}
