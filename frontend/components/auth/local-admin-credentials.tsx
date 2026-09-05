"use client"

import { useEffect, useState } from "react"
import { DEV_ADMIN_LOGIN, DEV_MEMBER_LOGIN } from "@/lib/dev-login"

type DevAccount = typeof DEV_ADMIN_LOGIN | typeof DEV_MEMBER_LOGIN

function isLocalBrowserHost(): boolean {
  if (typeof window === "undefined") return false
  const host = window.location.hostname.toLowerCase()
  return (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host === "[::1]"
  )
}

function AccountBlock({
  account,
  description,
  onUse,
}: {
  account: DevAccount
  description: string
  onUse?: (creds: { email: string; password: string }) => void
}) {
  return (
    <div className="text-left text-[0.8125rem]">
      <p className="font-medium text-foreground">{account.title}</p>
      <p className="mt-1 text-muted-foreground">{description}</p>
      <p className="mt-1 text-muted-foreground">
        Workspace{" "}
        <span className="font-mono text-foreground">{account.tenant}</span>
        {" · "}
        <span className="font-mono text-foreground">{account.email}</span>
        {" · "}
        <span className="font-mono text-foreground">{account.password}</span>
      </p>
      {onUse && (
        <button
          type="button"
          className="mt-2 text-ink-blue underline-offset-4 hover:underline"
          onClick={() =>
            onUse({
              email: account.email,
              password: account.password,
            })
          }
        >
          Fill {account.role} credentials
        </button>
      )}
    </div>
  )
}

/**
 * Seeded Alpha accounts for local testing.
 *
 * Gated on the browser hostname (localhost / loopback), not NODE_ENV.
 * `npm start` sets NODE_ENV=production, which previously hid this box
 * during local production-mode testing. Real deploys (vercel.app, a
 * product domain) still do not show it.
 */
export function LocalAdminCredentials({
  onUse,
  includeMember = false,
}: {
  onUse?: (creds: { email: string; password: string }) => void
  includeMember?: boolean
}) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    setVisible(isLocalBrowserHost())
  }, [])

  if (!visible) return null

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-yellow-200 bg-yellow-50 px-4 py-3">
      <AccountBlock
        account={DEV_ADMIN_LOGIN}
        description="Full access, including connectors, audit, and governance."
        onUse={onUse}
      />
      {includeMember && (
        <AccountBlock
          account={DEV_MEMBER_LOGIN}
          description="Regular employee account: search and document view."
          onUse={onUse}
        />
      )}
    </div>
  )
}
