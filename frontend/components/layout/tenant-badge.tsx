"use client"

import { useAuthStore } from "@/lib/auth/auth-store"

export function TenantBadge() {
  const claims = useAuthStore((s) => s.claims)

  if (!claims) return null

  // /me and the JWT only expose tenant_id (no display name yet) — show a
  // truncated id rather than inventing a tenant name we don't have.
  const shortId = claims.tenant_id.slice(0, 8)

  return (
    <div className="flex items-center gap-2 rounded-md border border-border-subtle bg-secondary/50 px-2.5 py-1.5 text-xs">
      <span className="size-1.5 rounded-full bg-success" aria-hidden />
      <span className="font-mono text-muted-foreground">{shortId}</span>
    </div>
  )
}
