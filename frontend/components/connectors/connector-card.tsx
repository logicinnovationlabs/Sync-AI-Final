"use client"

import { useEffect } from "react"
import { useSearchParams } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { motion } from "motion/react"
import { Plug, RefreshCw, Unplug } from "lucide-react"
import { ConnectorLogo } from "@/components/connector-logo"
import { Button } from "@/components/ui/button"
import {
  disconnectAllGooglePersonal,
  disconnectConnector,
  disconnectOrganizationConnector,
  getConnectorStatus,
  getGoogleAuthorizeUrl,
  getMicrosoftAuthorizeUrl,
  getOrganizationConnectorStatus,
  triggerOrganizationBackfill,
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

const MICROSOFT_SOURCES: { id: BackendSourceType; label: string }[] = [
  { id: "onedrive", label: "OneDrive" },
  { id: "outlook", label: "Outlook" },
]

function shouldPollConnectorStatus(status: ConnectorStatus | undefined): boolean {
  const connectionStatus = String(status?.details?.connection_status || "")
  if (connectionStatus === "syncing") return true
  if (status?.details?.token_present && connectionStatus !== "active") return true
  return false
}

function sourceIsLinked(status: ConnectorStatus | undefined): boolean {
  if (!status) return false
  const connectionStatus = String(status.details?.connection_status || "")
  const tokenPresent = Boolean(status.details?.token_present)
  // Explicit disconnect clears tokens; not_connected without a token is truly off.
  if (connectionStatus === "not_connected" && !tokenPresent) {
    return false
  }
  return (
    Boolean(status.cursor) ||
    tokenPresent ||
    ["active", "syncing", "error", "needs_reauth"].includes(connectionStatus)
  )
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
    queryFn: () => getConnectorStatus(token!, id, "personal"),
    enabled: hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: (query) =>
      shouldPollConnectorStatus(query.state.data) ? 3000 : false,
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
  const isSyncing =
    connectionStatus === "syncing" || backfill.isPending
  const statusLabel = !hydrated
    ? "Checking…"
    : !canRead
      ? "Needs connectors.read"
      : status.isPending && !status.data
        ? "Checking…"
        : isSyncing
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
            isSyncing
              ? filesIndexed > 0
                ? `Syncing · ${filesIndexed}`
                : "Syncing"
              : filesIndexed > 0
                ? `${filesIndexed} indexed`
                : started
                  ? "Started"
                  : "Not started"
          }
          on={started || isSyncing}
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
    refetchInterval: (query) =>
      String(query.state.data?.details?.connection_status || "") === "syncing"
        ? 3000
        : false,
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
  const isSyncing = connectionStatus === "syncing" || backfill.isPending
  const statusLabel = !hydrated
    ? "Checking…"
    : !canRead
      ? "Needs connectors.read"
      : status.isPending && !status.data
        ? "Checking…"
        : !orgEnabled
          ? "Disabled by admin"
          : isSyncing
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
            isSyncing
              ? filesIndexed > 0
                ? `Syncing · ${filesIndexed}`
                : "Syncing"
              : filesIndexed > 0
                ? `${filesIndexed} indexed`
                : started
                  ? "Started"
                  : "Not started"
          }
          on={started || isSyncing}
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
  const isMicrosoft = connector.source === "outlook"
  const googleLive = (isGooglePersonal || isGoogleOrganization) && connector.available
  const microsoftLive = isMicrosoft && connector.available

  // Personal Google status queries
  const driveStatus = useQuery({
    queryKey: ["connector-status", "google_drive"],
    queryFn: () => getConnectorStatus(token!, "google_drive", "personal"),
    enabled: isGooglePersonal && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: (query) =>
      shouldPollConnectorStatus(query.state.data) ? 3000 : false,
  })
  const gmailStatus = useQuery({
    queryKey: ["connector-status", "google_gmail"],
    queryFn: () => getConnectorStatus(token!, "google_gmail", "personal"),
    enabled: isGooglePersonal && googleLive && hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: (query) =>
      shouldPollConnectorStatus(query.state.data) ? 3000 : false,
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

  const googleLinked =
    isGooglePersonal &&
    googleLive &&
    (sourceIsLinked(driveStatus.data) || sourceIsLinked(gmailStatus.data))

  const disconnectGoogle = useMutation({
    mutationFn: () => disconnectAllGooglePersonal(token!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connector-status"] })
    },
  })

  const googleOrgLinked =
    isGoogleOrganization &&
    googleLive &&
    (orgDriveStatus.data?.details?.connected || orgGmailStatus.data?.details?.connected)

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

  const authorizeMicrosoft = useMutation({
    mutationFn: () => getMicrosoftAuthorizeUrl(token!),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

  const onedriveStatus = useQuery({
    queryKey: ["connector-status", "onedrive"],
    queryFn: () => getConnectorStatus(token!, "onedrive"),
    enabled: microsoftLive && hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: (query) =>
      shouldPollConnectorStatus(query.state.data) ? 3000 : false,
  })
  const outlookStatus = useQuery({
    queryKey: ["connector-status", "outlook"],
    queryFn: () => getConnectorStatus(token!, "outlook"),
    enabled: microsoftLive && hydrated && Boolean(token) && canRead,
    retry: false,
    refetchInterval: (query) =>
      shouldPollConnectorStatus(query.state.data) ? 3000 : false,
  })
  const microsoftLinked =
    microsoftLive &&
    (sourceIsLinked(onedriveStatus.data) || sourceIsLinked(outlookStatus.data))

  useEffect(() => {
    if (!isGooglePersonal && !isGoogleOrganization && !isMicrosoft) return
    const google = searchParams.get("google")
    const microsoft = searchParams.get("microsoft")
    if (!google && !microsoft) return
    queryClient.invalidateQueries({ queryKey: ["connector-status"] })
    const timer = window.setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ["connector-status"] })
    }, 3000)
    return () => window.clearInterval(timer)
  }, [connector.source, queryClient, searchParams, isGooglePersonal, isGoogleOrganization, isMicrosoft])

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
          {isMicrosoft && MICROSOFT_SOURCES.map((source) => (
            <GoogleSource key={source.id} {...source} />
          ))}
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
            : connector.handshake} · {connector.cadence}
        </p>
        {live && isGooglePersonal ? (
          hydrated && canWrite && (
            <div className="flex gap-1.5">
              {googleLinked ? (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={disconnectGoogle.isPending}
                    onClick={() => disconnectGoogle.mutate()}
                  >
                    <Unplug className="size-3.5" />
                    {disconnectGoogle.isPending ? "Disconnecting…" : "Disconnect"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={authorize.isPending}
                    onClick={() => authorize.mutate()}
                  >
                    <Plug className="size-3.5" />
                    {authorize.isPending ? "Opening…" : "Reconnect"}
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="default"
                  disabled={authorize.isPending}
                  onClick={() => authorize.mutate()}
                >
                  <Plug className="size-3.5" />
                  {authorize.isPending ? "Opening…" : "Connect"}
                </Button>
              )}
            </div>
          )
        ) : live && isMicrosoft ? (
          hydrated &&
          canWrite && (
            <Button
              size="sm"
              variant={microsoftLinked ? "outline" : "default"}
              disabled={authorizeMicrosoft.isPending}
              onClick={() => authorizeMicrosoft.mutate()}
            >
              <Plug className="size-3.5" />
              {authorizeMicrosoft.isPending
                ? "Opening…"
                : microsoftLinked
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
      {authorizeMicrosoft.error && isMicrosoft && (
        <p role="alert" className="text-[0.8125rem] text-destructive">
          {authorizeMicrosoft.error instanceof ApiError
            ? authorizeMicrosoft.error.message
            : "Couldn't start the Microsoft consent flow."}
        </p>
      )}
    </motion.li>
  )
}
