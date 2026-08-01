import { Suspense } from "react"
import Link from "next/link"
import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"

function SsoCallbackContent() {
  return (
    <div className="flex flex-col gap-6">
      <Alert>
        <AlertTriangle className="size-4" />
        <AlertTitle>SSO sign-in isn&apos;t fully wired up yet</AlertTitle>
        <AlertDescription>
          The backend exchanges the authorization code but doesn&apos;t yet
          issue a session from it — this is a known gap, not an error on
          your end. Use email/password sign-in for now.
        </AlertDescription>
      </Alert>

      <Button nativeButton={false} render={<Link href="/login">Back to sign in</Link>} />
    </div>
  )
}

export default function SsoCallbackPage() {
  return (
    <Suspense>
      <SsoCallbackContent />
    </Suspense>
  )
}
