import type { Metadata } from "next"
import { PageHeader } from "@/components/shared/page-header"
import { DocumentBrowser } from "@/components/documents/document-browser"

export const metadata: Metadata = {
  title: "Documents",
}

export default function DocumentsPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Documents" description="Every record SynQ can cite." />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <DocumentBrowser />
      </div>
    </div>
  )
}
