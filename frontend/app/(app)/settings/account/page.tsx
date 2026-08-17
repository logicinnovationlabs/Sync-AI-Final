import { PageHeader } from "@/components/shared/page-header"
import { AccountSettings } from "@/components/settings/account-settings"

export default function AccountSettingsPage() {
  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <PageHeader title="Account" description="Manage your sign-in details." />
      <AccountSettings />
    </div>
  )
}
