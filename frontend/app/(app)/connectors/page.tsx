import { Suspense } from "react"
import type { Metadata } from "next"
import { PageHeader } from "@/components/shared/page-header"
import { ConnectorList } from "@/components/connectors/connector-list"

export const metadata: Metadata = {
  title: "Connectors",
}

export default function ConnectorsPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Connectors"
        description="Connect your personal Google account for private search, or access organization-wide content if enabled by your admin."
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <Suspense fallback={<p className="px-6 py-8 text-sm text-muted-foreground">Loading connectors…</p>}>
          <ConnectorList />
        </Suspense>
      </div>
    </div>
  )
}
