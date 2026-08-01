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
        description="What SynQ reads, and how often."
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ConnectorList />
      </div>
    </div>
  )
}
