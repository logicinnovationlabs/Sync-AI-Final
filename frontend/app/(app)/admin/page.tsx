import { PageHeader } from "@/components/shared/page-header"
import { AdminConsole } from "@/components/admin/admin-console"

export default function AdminOverviewPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Admin"
        description="Users and audit log from Block N."
      />
      <AdminConsole />
    </div>
  )
}
