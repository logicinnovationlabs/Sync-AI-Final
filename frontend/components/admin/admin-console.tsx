"use client"

import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { listAuditLogs, listPendingIdentities } from "@/lib/api/admin"
import {
  connectOrganizationConnector,
  disconnectOrganizationConnector,
  toggleOrganizationConnector,
  getOrganizationConnectorStatus,
  connectSharePointOrganization,
  disconnectSharePointOrganization,
  toggleSharePointOrganization,
  triggerSharePointOrganizationBackfill,
  type OrganizationConnectRequest,
  type SharePointConnectRequest,
} from "@/lib/api/connectors"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
import { Button } from "@/components/ui/button"
import { MembersPanel } from "@/components/admin/members-panel"

export function AdminConsole() {
  const token = useAuthStore((s) => s.accessToken)
  const queryClient = useQueryClient()
  const [vaultKey, setVaultKey] = useState("")
  const [impersonateEmail, setImpersonateEmail] = useState("")
  const [sharepointVaultKey, setSharepointVaultKey] = useState("")
  const [sharepointSiteUrl, setSharepointSiteUrl] = useState("")

  const audit = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => listAuditLogs(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const pendingIdentities = useQuery({
    queryKey: ["admin-pending-identities"],
    queryFn: () => listPendingIdentities(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const orgDriveStatus = useQuery({
    queryKey: ["org-status", "google_drive"],
    queryFn: () => getOrganizationConnectorStatus(token!, "google_drive"),
    enabled: Boolean(token),
    retry: false,
  })

  const sharepointStatus = useQuery({
    queryKey: ["org-status", "sharepoint"],
    queryFn: () => getOrganizationConnectorStatus(token!, "sharepoint"),
    enabled: Boolean(token),
    retry: false,
  })

  const connectMutation = useMutation({
    mutationFn: (request: OrganizationConnectRequest) =>
      connectOrganizationConnector(token!, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status"] })
      setVaultKey("")
      setImpersonateEmail("")
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: () => disconnectOrganizationConnector(token!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status"] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      toggleOrganizationConnector(token!, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status"] })
    },
  })

  const sharepointConnectMutation = useMutation({
    mutationFn: (request: SharePointConnectRequest) =>
      connectSharePointOrganization(token!, request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status", "sharepoint"] })
      setSharepointVaultKey("")
      setSharepointSiteUrl("")
    },
  })

  const sharepointDisconnectMutation = useMutation({
    mutationFn: () => disconnectSharePointOrganization(token!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status", "sharepoint"] })
    },
  })

  const sharepointToggleMutation = useMutation({
    mutationFn: (enabled: boolean) => toggleSharePointOrganization(token!, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status", "sharepoint"] })
    },
  })

  const sharepointSyncMutation = useMutation({
    mutationFn: () => triggerSharePointOrganizationBackfill(token!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-status", "sharepoint"] })
    },
  })

  const orgEnabled = Boolean(orgDriveStatus.data?.details?.org_enabled)
  const orgConnected = Boolean(orgDriveStatus.data?.details?.connected)
  const sharepointEnabled = Boolean(sharepointStatus.data?.details?.org_enabled)
  const sharepointConnected = Boolean(sharepointStatus.data?.details?.connected)
  const sharepointFiles = Number(sharepointStatus.data?.details?.files_indexed || 0)
  const sharepointSyncing =
    String(sharepointStatus.data?.details?.connection_status || "") === "syncing"

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-8">
      <section>
        <h2 className="text-sm font-medium">Organization Google Workspace</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Admin-managed service account connector with ACL-mirrored permissions
        </p>

        <div className="mt-4 rounded-2xl border border-border-subtle p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Status</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {orgConnected ? "Connected" : "Not connected"} · {orgEnabled ? "Enabled" : "Disabled"}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => toggleMutation.mutate(!orgEnabled)}
                disabled={toggleMutation.isPending || !orgConnected}
              >
                {toggleMutation.isPending ? "Toggling…" : orgEnabled ? "Disable" : "Enable"}
              </Button>
              {orgConnected && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => disconnectMutation.mutate()}
                  disabled={disconnectMutation.isPending}
                >
                  {disconnectMutation.isPending ? "Disconnecting…" : "Disconnect"}
                </Button>
              )}
            </div>
          </div>

          {!orgConnected && (
            <div className="mt-4 border-t border-border-subtle pt-4">
              <p className="mb-3 text-sm font-medium">Connect Service Account</p>
              <div className="flex flex-col gap-3">
                <input
                  type="text"
                  placeholder="Vault key name (e.g., kv/tenant/google-service-account)"
                  value={vaultKey}
                  onChange={(e) => setVaultKey(e.target.value)}
                  className="rounded-md border border-border px-3 py-2 text-sm"
                />
                <input
                  type="email"
                  placeholder="Impersonate email (e.g., admin@company.com)"
                  value={impersonateEmail}
                  onChange={(e) => setImpersonateEmail(e.target.value)}
                  className="rounded-md border border-border px-3 py-2 text-sm"
                />
                <Button
                  size="sm"
                  onClick={() =>
                    connectMutation.mutate({ vault_key: vaultKey, impersonate_email: impersonateEmail })
                  }
                  disabled={connectMutation.isPending || !vaultKey || !impersonateEmail}
                >
                  {connectMutation.isPending ? "Connecting…" : "Connect"}
                </Button>
              </div>
              {connectMutation.error && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  {connectMutation.error instanceof ApiError
                    ? connectMutation.error.message
                    : "Failed to connect"}
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium">Organization SharePoint</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Admin-managed Microsoft Graph service principal with ACL-mirrored permissions
        </p>

        <div className="mt-4 rounded-2xl border border-border-subtle p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Status</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {sharepointConnected ? "Connected" : "Not connected"} ·{" "}
                {sharepointEnabled ? "Enabled" : "Disabled"}
                {sharepointConnected
                  ? ` · ${sharepointFiles} file${sharepointFiles === 1 ? "" : "s"} indexed`
                  : ""}
                {sharepointSyncing ? " · Syncing" : ""}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => sharepointToggleMutation.mutate(!sharepointEnabled)}
                disabled={sharepointToggleMutation.isPending || !sharepointConnected}
              >
                {sharepointToggleMutation.isPending
                  ? "Toggling…"
                  : sharepointEnabled
                    ? "Disable"
                    : "Enable"}
              </Button>
              {sharepointConnected && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => sharepointSyncMutation.mutate()}
                  disabled={sharepointSyncMutation.isPending || sharepointSyncing}
                >
                  {sharepointSyncMutation.isPending || sharepointSyncing ? "Syncing…" : "Sync"}
                </Button>
              )}
              {sharepointConnected && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => sharepointDisconnectMutation.mutate()}
                  disabled={sharepointDisconnectMutation.isPending}
                >
                  {sharepointDisconnectMutation.isPending ? "Disconnecting…" : "Disconnect"}
                </Button>
              )}
            </div>
          </div>

          {!sharepointConnected && (
            <div className="mt-4 border-t border-border-subtle pt-4">
              <p className="mb-3 text-sm font-medium">Connect Service Principal</p>
              <div className="flex flex-col gap-3">
                <input
                  type="text"
                  placeholder="Vault key name (e.g., kv/tenant/dev-fake-sharepoint-app)"
                  value={sharepointVaultKey}
                  onChange={(e) => setSharepointVaultKey(e.target.value)}
                  className="rounded-md border border-border px-3 py-2 text-sm"
                />
                <input
                  type="text"
                  placeholder="Site URL (optional — leave blank for all sites)"
                  value={sharepointSiteUrl}
                  onChange={(e) => setSharepointSiteUrl(e.target.value)}
                  className="rounded-md border border-border px-3 py-2 text-sm"
                />
                <Button
                  size="sm"
                  onClick={() =>
                    sharepointConnectMutation.mutate({
                      vault_key: sharepointVaultKey,
                      site_url: sharepointSiteUrl || undefined,
                    })
                  }
                  disabled={sharepointConnectMutation.isPending || !sharepointVaultKey}
                >
                  {sharepointConnectMutation.isPending ? "Connecting…" : "Connect"}
                </Button>
              </div>
              {sharepointConnectMutation.error && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  {sharepointConnectMutation.error instanceof ApiError
                    ? sharepointConnectMutation.error.message
                    : "Failed to connect"}
                </p>
              )}
            </div>
          )}
          {sharepointSyncMutation.error && (
            <p role="alert" className="mt-2 text-xs text-destructive">
              {sharepointSyncMutation.error instanceof ApiError
                ? sharepointSyncMutation.error.message
                : "Sync failed"}
            </p>
          )}
        </div>
      </section>

      <MembersPanel />

      <section>
        <h2 className="text-sm font-medium">Audit log</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Recent admin actions in this workspace.
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

      <section>
        <h2 className="text-sm font-medium">Pending identities</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Share emails that have not been matched to a workspace account yet.
        </p>
        {pendingIdentities.isFetching && (
          <p className="mt-3 text-sm text-muted-foreground">Loading pending identities…</p>
        )}
        {pendingIdentities.error && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            {pendingIdentities.error instanceof ApiError
              ? pendingIdentities.error.message
              : "Failed to load pending identities"}
          </p>
        )}
        {pendingIdentities.data && (
          <ul className="mt-3 divide-y divide-border-subtle rounded-2xl border border-border-subtle">
            {pendingIdentities.data.length === 0 ? (
              <li className="px-4 py-3 text-sm text-muted-foreground">
                No pending identities for this tenant.
              </li>
            ) : (
              pendingIdentities.data.map((item, index) => (
                <li key={`${item.document_id}-${item.shared_email}-${index}`} className="px-4 py-3 text-sm">
                  <span className="font-medium">{item.shared_email}</span>
                  <span className="ml-2 text-muted-foreground">
                    Document: {item.document_id}
                  </span>
                  {item.first_seen_at && (
                    <span className="ml-2 text-muted-foreground">
                      First seen: {new Date(item.first_seen_at).toLocaleString()}
                    </span>
                  )}
                </li>
              ))
            )}
          </ul>
        )}
      </section>
    </div>
  )
}
