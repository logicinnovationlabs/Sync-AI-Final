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
        description="Connect your own Google account. Drive and Gmail stay private to you — other members and admins cannot search them."
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        <ConnectorList />
      </div>
    </div>
  )
}
