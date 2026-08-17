"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { changePassword, getMe } from "@/lib/api/auth"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function AccountSettings() {
  const token = useAuthStore((s) => s.accessToken)
  const email = useAuthStore((s) => s.email)
  const [oldPassword, setOldPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => getMe(token!),
    enabled: Boolean(token),
    retry: false,
  })

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!token) return
    setSaving(true)
    setError(null)
    setStatus(null)
    try {
      const res = await changePassword(token, {
        old_password: oldPassword,
        new_password: newPassword,
      })
      setStatus(res.message)
      setOldPassword("")
      setNewPassword("")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Password change failed")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-border-subtle p-4">
        <h2 className="text-sm font-medium">Session</h2>
        <p className="mt-1 text-xs text-muted-foreground">GET /api/v1/me</p>
        {me.error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {me.error instanceof ApiError ? me.error.message : "Could not load /me"}
          </p>
        )}
        {me.data && (
          <dl className="mt-3 space-y-1 text-sm">
            <div>
              <dt className="text-muted-foreground">Email (from login)</dt>
              <dd>{email ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Principal</dt>
              <dd className="font-mono text-[0.75rem]">{me.data.principal_id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Tenant</dt>
              <dd className="font-mono text-[0.75rem]">{me.data.tenant_id}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Role</dt>
              <dd>{me.data.role ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Scopes</dt>
              <dd className="font-mono text-[0.75rem]">
                {(me.data.scopes || []).join(", ") || "—"}
              </dd>
            </div>
          </dl>
        )}
      </section>

      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-3 rounded-2xl border border-border-subtle p-4"
      >
        <h2 className="text-sm font-medium">Change password</h2>
        <p className="text-xs text-muted-foreground">
          POST /api/v1/me/change-password
        </p>
        <Input
          type="password"
          autoComplete="current-password"
          placeholder="Current password"
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
          required
        />
        <Input
          type="password"
          autoComplete="new-password"
          placeholder="New password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {status && <p className="text-sm text-muted-foreground">{status}</p>}
        <Button type="submit" disabled={saving || !token}>
          {saving ? "Saving…" : "Update password"}
        </Button>
      </form>
    </div>
  )
}
