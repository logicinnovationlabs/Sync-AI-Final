import { PageHeader } from "@/components/shared/page-header"

export default function AccountSettingsPage() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Account" description="Manage your sign-in details." />
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Account settings — coming up.
      </div>
    </div>
  )
}
