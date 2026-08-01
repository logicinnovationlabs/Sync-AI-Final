import Link from "next/link"
import { ShieldX } from "lucide-react"
import { Button } from "@/components/ui/button"

export function PermissionDenied({
  requiredScope,
}: {
  requiredScope?: string
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-24 text-center">
      <ShieldX className="size-8 text-muted-foreground" />
      <h1 className="text-lg font-medium">You don&apos;t have access to this</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        {requiredScope
          ? `This page requires the "${requiredScope}" scope, which your account doesn't have.`
          : "This page is restricted to tenant admins."}
      </p>
      <Button
        variant="outline"
        size="sm"
        nativeButton={false}
        render={<Link href="/chat">Back to chat</Link>}
      />
    </div>
  )
}
