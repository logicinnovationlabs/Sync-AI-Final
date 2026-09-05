"use client"

import { useEffect } from "react"
import { useSearchParams } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { motion } from "motion/react"
import { Plug, RefreshCw, Unplug } from "lucide-react"
import { ConnectorLogo } from "@/components/connector-logo"
import { Button } from "@/components/ui/button"
import {
  disconnectConnector,
  disconnectOrganizationConnector,
  getConnectorStatus,
  getGoogleAuthorizeUrl,
  getOrganizationConnectorStatus,
  getSharePointAuthorizeUrl,
  triggerOrganizationBackfill,
  triggerSharePointOrganizationBackfill,
  triggerBackfill,
  type BackendSourceType,
  type ConnectorStatus,
} from "@/lib/api/connectors"
import { ApiError } from "@/lib/api/client"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { hasScope, SCOPES } from "@/lib/auth/scopes"
import type { ConnectorMeta } from "@/lib/connectors"
import { EASE_OUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * One connector, as a card.
 *
 * ── On the stat tiles ────────────────────────────────────────────────────────
 * The obvious tiles are "files indexed" and "last sync". We can't show either:
 * `GET /connectors/{source}/status` returns `cursor`, `watch_active` and
 * `details`, and there is no count and no timestamp anywhere in that response
 * (`backend/app/connectors/router.py`). So the tiles report what the API
 * actually knows — whether ingestion has started, and whether live updates are
 * on. A fabricated file count is the one thing this card must never show.
 *
 * Every connector gets the full card. Sources without a backend integration
 * still show their real handshake and cadence from `lib/connectors.ts` and a
 * Connect button; pressing it says what's missing rather than the card wearing
 * a permanent "unavailable" label.
 */

const GOOGLE_SOURCES: { id: BackendSourceType; label: string }[] = [
  { id: "google_drive", label: "Drive" },
  { id: "google_gmail", label: "Gmail" },
]

const GOOGLE_ORGANIZATION_SOURCES: { id: BackendSourceType; label: string }[] = [
  { id: "google_drive", label: "Drive" },
  { id: "google_gmail", label: "Gmail" },
]

const SHAREPOINT_SOURCES: { id: BackendSourceType; label: string }[] = [
  { id: "sharepoint", label: "Libraries" },
]

function sourceIsLinked(status: ConnectorStatus | undefined): boolean {
  const connectionStatus = String(status?.details?.connection_status || "")
  return (
    Boolean(status?.cursor) ||
    Boolean(status?.details?.token_present) ||
    ["active", "syncing"].includes(connectionStatus)
  )
}

function connectedStatusRefetchInterval(query: {
  state: { data?: ConnectorStatus }
}): number | false {
  const st = String(query.state.data?.details?.connection_status || "")
  if (st === "syncing") return 2500
  if (st === "active") return 15000
  return false
}

function StatTile({ label, value, on }: { label: string; value: string; on: boolean }) {
  return (
    <div className="flex-1 rounded-[0.875rem] border border-border-subtle px-3 py-2.5">
      <p className="font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-[0.8125rem] font-medium">
        <span
          aria-hidden
          className={cn(
            "size-1.5 shrink-0 rounded-full",
            on ? "bg-success" : "bg-muted-foreground/40"
          )}
        />
        {value}
      </p>
    </div>
  )
}

function GoogleSource({ id, label }: { id: BackendSourceType; label: string }) {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  // Select the *boolean*, not the array. `effectiveScopes()` builds a new array
  // on every call, so a selector returning it changes identity every render and
  // zustand's useSyncExternalStore spins.
  const canRead = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_READ)
  )
  const canWrite = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_WRITE)
  )
  const queryClient = useQueryClient()

  const status = useQuery({
    queryKey: ["connector-status", id],
    queryFn: () => getConnectorStatus(token!, id),
    enabled: hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: connectedStatusRefetchInterval,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["connector-status", id] })

  const backfill = useMutation({
    mutationFn: () => triggerBackfill(token!, id),
    onSuccess: invalidate,
  })
  const disconnect = useMutation({
    mutationFn: () => disconnectConnector(token!, id),
    onSuccess: invalidate,
  })

  const started = sourceIsLinked(status.data)
  const watching = Boolean(status.data?.watch_active)
  const connectionStatus = String(status.data?.details?.connection_status || "")
  const filesIndexed = Number(status.data?.details?.files_indexed || 0)
  const statusLabel = !hydrated
    ? "Checking…"
    : !canRead
      ? "Needs connectors.read"
      : status.isPending
        ? "Checking…"
        : connectionStatus === "syncing"
          ? "Syncing"
          : connectionStatus === "needs_reauth"
            ? "Needs re-auth"
            : connectionStatus === "error"
              ? "Error"
              : started || connectionStatus === "active"
                ? "Connected"
                : "Not connected"

  return (
    <div className="flex flex-col gap-2.5 rounded-[1rem] bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.8125rem] font-medium">{label}</span>
        {status.error ? (
          <span className="text-[0.75rem] text-destructive">
            {status.error instanceof ApiError
              ? status.error.message
              : "Couldn't reach the API"}
          </span>
        ) : (
          <span className="text-[0.75rem] text-muted-foreground">
            {statusLabel}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <StatTile
          label="Ingestion"
          value={
            connectionStatus === "syncing"
              ? "Syncing"
              : filesIndexed > 0
                ? `${filesIndexed} indexed`
                : started
                  ? "Started"
                  : "Not started"
          }
          on={started || connectionStatus === "syncing"}
        />
        <StatTile
          label="Live updates"
          value={watching ? "On" : "Off"}
          on={watching}
        />
      </div>

      {hydrated && canWrite && !status.error && (
        <div className="flex justify-end gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={backfill.isPending}
            onClick={() => backfill.mutate()}
          >
            <RefreshCw
              className={cn("size-3.5", backfill.isPending && "animate-spin")}
            />
            {backfill.isPending ? "Syncing…" : "Resync"}
          </Button>
          {started && (
            <Button
              size="sm"
              variant="ghost"
              disabled={disconnect.isPending}
              onClick={() => disconnect.mutate()}
            >
              <Unplug className="size-3.5" />
              Disconnect
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function GoogleOrganizationSource({ id, label }: { id: BackendSourceType; label: string }) {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const canRead = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_READ)
  )
  const canWrite = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_WRITE)
  )
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const queryClient = useQueryClient()

  const status = useQuery({
    queryKey: ["connector-status", "organization", id],
    queryFn: () => getOrganizationConnectorStatus(token!, id),
    enabled: hydrated && Boolean(token) && canRead,
    retry: false,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["connector-status", "organization", id] })

  const authorize = useMutation({
    mutationFn: () => getGoogleAuthorizeUrl(token!, "organization"),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

  const backfill = useMutation({
    mutationFn: () => triggerOrganizationBackfill(token!, id),
    onSuccess: invalidate,
  })
  const disconnect = useMutation({
    mutationFn: () => disconnectOrganizationConnector(token!),
    onSuccess: invalidate,
  })

  const started = Boolean(status.data?.details?.connected)
  const orgEnabled = Boolean(status.data?.details?.org_enabled)
  const watching = Boolean(status.data?.watch_active)
  const connectionStatus = String(status.data?.details?.connection_status || "")
  const filesIndexed = Number(status.data?.details?.files_indexed || 0)
  const statusLabel = !hydrated
    ? "Checking…"
    : !canRead
      ? "Needs connectors.read"
      : status.isPending
        ? "Checking…"
        : !orgEnabled
          ? "Disabled by admin"
          : connectionStatus === "syncing"
            ? "Syncing"
            : connectionStatus === "error"
              ? "Error"
              : started || connectionStatus === "active"
                ? "Connected"
                : "Not connected"

  return (
    <div className="flex flex-col gap-2.5 rounded-[1rem] bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.8125rem] font-medium">{label}</span>
        {status.error ? (
          <span className="text-[0.75rem] text-destructive">
            {status.error instanceof ApiError
              ? status.error.message
              : "Couldn't reach the API"}
          </span>
        ) : (
          <span className="text-[0.75rem] text-muted-foreground">
            {statusLabel}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <StatTile
          label="Ingestion"
          value={
            connectionStatus === "syncing"
              ? "Syncing"
              : filesIndexed > 0
                ? `${filesIndexed} indexed`
                : started
                  ? "Started"
                  : "Not started"
          }
          on={started || connectionStatus === "syncing"}
        />
        <StatTile
          label="Live updates"
          value={watching ? "On" : "Off"}
          on={watching}
        />
      </div>

      {hydrated && canWrite && isAdmin && !status.error && (
        <div className="flex justify-end gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={!orgEnabled || backfill.isPending}
            onClick={() => backfill.mutate()}
          >
            <RefreshCw className={cn("size-3.5", backfill.isPending && "animate-spin")} />
            {backfill.isPending ? "Syncing…" : "Resync"}
          </Button>
          {started && (
            <Button
              size="sm"
              variant="ghost"
              disabled={!orgEnabled || disconnect.isPending}
              onClick={() => disconnect.mutate()}
            >
              <Unplug className="size-3.5" />
              {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function SharePointOrganizationSource() {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const canRead = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_READ)
  )
  const canWrite = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_WRITE)
  )
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const queryClient = useQueryClient()

  const status = useQuery({
    queryKey: ["connector-status", "organization", "sharepoint"],
    queryFn: () => getOrganizationConnectorStatus(token!, "sharepoint"),
    enabled: hydrated && Boolean(token) && canRead,
    retry: false,
  })

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["connector-status", "organization", "sharepoint"] })

  const backfill = useMutation({
    mutationFn: () => triggerSharePointOrganizationBackfill(token!),
    onSuccess: invalidate,
  })

  const started = Boolean(status.data?.details?.connected)
  const orgEnabled = Boolean(status.data?.details?.org_enabled)
  const connectionStatus = String(status.data?.details?.connection_status || "")
  const filesIndexed = Number(status.data?.details?.files_indexed || 0)
  const statusLabel = !hydrated
    ? "Checking…"
    : !canRead
      ? "Needs connectors.read"
      : status.isPending
        ? "Checking…"
        : !orgEnabled
          ? "Disabled by admin"
          : connectionStatus === "syncing"
            ? "Syncing"
            : connectionStatus === "error"
              ? "Error"
              : started || connectionStatus === "active"
                ? "Connected"
                : "Not connected"

  return (
    <div className="flex flex-col gap-2.5 rounded-[1rem] bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.8125rem] font-medium">Libraries</span>
        {status.error ? (
          <span className="text-[0.75rem] text-destructive">
            {status.error instanceof ApiError
              ? status.error.message
              : "Couldn't reach the API"}
          </span>
        ) : (
          <span className="text-[0.75rem] text-muted-foreground">{statusLabel}</span>
        )}
      </div>
      <div className="flex gap-2">
        <StatTile
          label="Ingestion"
          value={
            connectionStatus === "syncing"
              ? "Syncing"
              : filesIndexed > 0
                ? `${filesIndexed} indexed`
                : started
                  ? "Started"
                  : "Not started"
          }
          on={started || connectionStatus === "syncing"}
        />
        <StatTile label="Live updates" value="On sync" on={started} />
      </div>
      {hydrated && canWrite && isAdmin && started && !status.error && (
        <div className="flex justify-end gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={backfill.isPending || !orgEnabled}
            onClick={() => backfill.mutate()}
          >
            <RefreshCw className={cn("size-3.5", backfill.isPending && "animate-spin")} />
            {backfill.isPending ? "Syncing…" : "Resync"}
          </Button>
        </div>
      )}
    </div>
  )
}

export function ConnectorCard({
  connector,
  index,
}: {
  connector: ConnectorMeta
  index: number
}) {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const canRead = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_READ)
  )
  const canWrite = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_WRITE)
  )
  const isAdmin = useAuthStore((s) => s.isAdmin())

  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const isGooglePersonal = connector.source === "google_personal"
  const isGoogleOrganization = connector.source === "google_organization"
  const isSharePointPersonal = connector.source === "sharepoint_personal"
  const isSharePointOrganization = connector.source === "sharepoint_organization"
  const googleLive = (isGooglePersonal || isGoogleOrganization) && connector.available
  const sharepointLive =
    (isSharePointPersonal || isSharePointOrganization) && connector.available

  // Personal Google status queries
  const driveStatus = useQuery({
    queryKey: ["connector-status", "google_drive"],
    queryFn: () => getConnectorStatus(token!, "google_drive", "personal"),
    enabled: isGooglePersonal && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
  })
  const gmailStatus = useQuery({
    queryKey: ["connector-status", "google_gmail"],
    queryFn: () => getConnectorStatus(token!, "google_gmail", "personal"),
    enabled: isGooglePersonal && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
  })

  // Organization Google status is read-only for members
  const orgDriveStatus = useQuery({
    queryKey: ["connector-status", "organization", "google_drive"],
    queryFn: () => getOrganizationConnectorStatus(token!, "google_drive"),
    enabled: isGoogleOrganization && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
  })
  const orgGmailStatus = useQuery({
    queryKey: ["connector-status", "organization", "google_gmail"],
    queryFn: () => getOrganizationConnectorStatus(token!, "google_gmail"),
    enabled: isGoogleOrganization && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
  })

  const sharepointPersonalStatus = useQuery({
    queryKey: ["connector-status", "sharepoint"],
    queryFn: () => getConnectorStatus(token!, "sharepoint", "personal"),
    enabled: isSharePointPersonal && sharepointLive && hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: connectedStatusRefetchInterval,
  })

  const sharepointOrgStatus = useQuery({
    queryKey: ["connector-status", "organization", "sharepoint"],
    queryFn: () => getOrganizationConnectorStatus(token!, "sharepoint"),
    enabled:
      isSharePointOrganization && sharepointLive && hydrated && Boolean(token) && canRead,
    retry: false,
  })

  const googleLinked =
    isGooglePersonal &&
    googleLive &&
    (sourceIsLinked(driveStatus.data) || sourceIsLinked(gmailStatus.data))

  const googleOrgLinked =
    isGoogleOrganization &&
    googleLive &&
    (orgDriveStatus.data?.details?.connected || orgGmailStatus.data?.details?.connected)

  const sharepointLinked =
    isSharePointPersonal && sharepointLive && sourceIsLinked(sharepointPersonalStatus.data)
  const sharepointOrgLinked =
    isSharePointOrganization &&
    sharepointLive &&
    Boolean(sharepointOrgStatus.data?.details?.connected)

  const authorize = useMutation({
    mutationFn: () => getGoogleAuthorizeUrl(token!, "personal"),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

  const authorizeOrg = useMutation({
    mutationFn: () => getGoogleAuthorizeUrl(token!, "organization"),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

  const authorizeSharePoint = useMutation({
    mutationFn: () => getSharePointAuthorizeUrl(token!),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

  useEffect(() => {
    if (!isGooglePersonal && !isGoogleOrganization && !isSharePointPersonal && !isSharePointOrganization) return
    const google = searchParams.get("google")
    const sharepoint = searchParams.get("sharepoint")
    if (!google && !sharepoint) return
    queryClient.invalidateQueries({ queryKey: ["connector-status"] })
  }, [
    connector.source,
    queryClient,
    searchParams,
    isGooglePersonal,
    isGoogleOrganization,
    isSharePointPersonal,
    isSharePointOrganization,
  ])

  const live = connector.available

  return (
    <motion.li
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE_OUT, delay: index * 0.04 }}
      className="flex flex-col gap-4 rounded-[1.5rem] border border-border-subtle bg-card p-5 transition-shadow duration-200 hover:shadow-[0_10px_40px_-16px_oklch(0.3_0.04_275/0.18)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3.5">
          <ConnectorLogo source={connector.source} className="size-10 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-[0.9375rem] font-medium">{connector.name}</h2>
            <p className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
              {connector.description}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.6875rem] font-medium",
            live ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
          )}
        >
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full",
              live ? "bg-success" : "bg-muted-foreground/50"
            )}
          />
          {live ? "Available" : "In rollout"}
        </span>
      </div>

      {live ? (
        <div className="flex flex-col gap-2">
          {isGooglePersonal && GOOGLE_SOURCES.map((source) => (
            <GoogleSource key={source.id} {...source} />
          ))}
          {isGoogleOrganization && GOOGLE_ORGANIZATION_SOURCES.map((source) => (
            <GoogleOrganizationSource key={source.id} {...source} />
          ))}
          {isSharePointPersonal && SHAREPOINT_SOURCES.map((source) => (
            <GoogleSource key={source.id} {...source} />
          ))}
          {isSharePointOrganization && <SharePointOrganizationSource />}
        </div>
      ) : (
        <div className="flex gap-2">
          <StatTile label="Ingestion" value="Not started" on={false} />
          <StatTile label="Live updates" value="Off" on={false} />
        </div>
      )}

      <div className="flex items-center justify-between gap-3 border-t border-border-subtle pt-3.5">
        <p className="font-mono text-[0.6875rem] text-muted-foreground">
          {isGoogleOrganization && googleOrgLinked
            ? "OAuth (admin) · Polled every ~3 min"
            : isSharePointOrganization && sharepointOrgLinked
              ? "Service principal · Polled on sync"
              : `${connector.handshake} · ${connector.cadence}`}
        </p>
        {live && isGooglePersonal ? (
          hydrated && canWrite && (
            <Button
              size="sm"
              variant={googleLinked ? "outline" : "default"}
              disabled={authorize.isPending}
              onClick={() => authorize.mutate()}
            >
              <Plug className="size-3.5" />
              {authorize.isPending
                ? "Opening…"
                : googleLinked
                  ? "Reconnect"
                  : "Connect"}
            </Button>
          )
        ) : live && isGoogleOrganization ? (
          hydrated && canWrite && isAdmin ? (
            <Button
              size="sm"
              variant={googleOrgLinked ? "outline" : "default"}
              disabled={authorizeOrg.isPending}
              onClick={() => authorizeOrg.mutate()}
            >
              <Plug className="size-3.5" />
              {authorizeOrg.isPending
                ? "Opening…"
                : googleOrgLinked
                  ? "Reconnect"
                  : "Connect"}
            </Button>
          ) : (
            <Button size="sm" variant="outline" disabled>
              <Plug className="size-3.5" />
              Admin-managed
            </Button>
          )
        ) : live && isSharePointPersonal ? (
          hydrated && canWrite && (
            <Button
              size="sm"
              variant={sharepointLinked ? "outline" : "default"}
              disabled={authorizeSharePoint.isPending}
              onClick={() => authorizeSharePoint.mutate()}
            >
              <Plug className="size-3.5" />
              {authorizeSharePoint.isPending
                ? "Opening…"
                : sharepointLinked
                  ? "Reconnect"
                  : "Connect"}
            </Button>
          )
        ) : live && isSharePointOrganization ? (
          <Button size="sm" variant="outline" disabled>
            <Plug className="size-3.5" />
            Admin-managed
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled>
            <Plug className="size-3.5" />
            Connect
          </Button>
        )}
      </div>

      {authorize.error && isGooglePersonal && (
        <p role="alert" className="text-[0.8125rem] text-destructive">
          {authorize.error instanceof ApiError
            ? authorize.error.message
            : "Couldn't start the Google consent flow."}
        </p>
      )}
      {authorizeSharePoint.error && isSharePointPersonal && (
        <p role="alert" className="text-[0.8125rem] text-destructive">
          {authorizeSharePoint.error instanceof ApiError
            ? authorizeSharePoint.error.message
            : "Couldn't start the Microsoft consent flow."}
        </p>
      )}
    </motion.li>
  )
}
