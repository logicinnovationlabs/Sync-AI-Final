"use client"

import { useQuery } from "@tanstack/react-query"
import { listAdminUsers, listAuditLogs } from "@/lib/api/admin"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"

export function AdminConsole() {
  const token = useAuthStore((s) => s.accessToken)

  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => listAdminUsers(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const audit = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => listAuditLogs(token!),
    enabled: Boolean(token),
    retry: false,
  })

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-8">
      <section>
        <h2 className="text-sm font-medium">Users</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          GET /api/v1/admin/users — Block N, require_admin
        </p>
        {users.isFetching && (
          <p className="mt-3 text-sm text-muted-foreground">Loading users…</p>
        )}
        {users.error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {users.error instanceof ApiError
              ? users.error.message
              : "Failed to load users"}
          </p>
        )}
        {users.data && (
          <ul className="mt-3 divide-y divide-border-subtle rounded-2xl border border-border-subtle">
            {users.data.map((user) => (
              <li key={user.principal_id} className="px-4 py-3 text-sm">
                <span className="font-medium">{user.display_name}</span>
                <span className="text-muted-foreground"> · {user.email}</span>
                <span className="ml-2 font-mono text-[0.6875rem] text-muted-foreground">
                  {user.role}
                  {user.is_active ? "" : " · inactive"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium">Audit log</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          GET /api/v1/admin/audit — Block N
        </p>
        {audit.isFetching && (
          <p className="mt-3 text-sm text-muted-foreground">Loading audit…</p>
        )}
        {audit.error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {audit.error instanceof ApiError
              ? audit.error.message
              : "Failed to load audit"}
          </p>
        )}
        {audit.data && (
          <ul className="mt-3 divide-y divide-border-subtle rounded-2xl border border-border-subtle">
            {audit.data.items.length === 0 ? (
              <li className="px-4 py-3 text-sm text-muted-foreground">
                No audit rows for this tenant.
              </li>
            ) : (
              audit.data.items.map((row) => (
                <li key={row.id} className="px-4 py-3 text-sm">
                  <span className="font-mono text-[0.75rem]">{row.action_type}</span>
                  <span className="ml-2 text-muted-foreground">
                    {new Date(row.created_at).toLocaleString()}
                  </span>
                </li>
              ))
            )}
          </ul>
        )}
      </section>
    </div>
  )
}
