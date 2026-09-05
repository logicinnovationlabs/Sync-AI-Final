import { PageHeader } from "@/components/shared/page-header"
import { AdminConsole } from "@/components/admin/admin-console"

export default function AdminOverviewPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Admin"
        description="Every member in this workspace, with per-document access control."
      />
      {/* AppShell clips overflow. Documents/Connectors scroll this way; without
          it the member document-access list was rendered but unreachable. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <AdminConsole />
      </div>
    </div>
  )
}
