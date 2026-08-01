import { PageHeader } from "@/components/shared/page-header"

export default function AdminOverviewPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Admin"
        description="AI keys, tenant users, and usage."
      />
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Admin console — coming up.
      </div>
    </div>
  )
}
