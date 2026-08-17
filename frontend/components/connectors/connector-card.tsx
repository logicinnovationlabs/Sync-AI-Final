"use client"

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { motion } from "motion/react"
import { Plug, RefreshCw, Unplug } from "lucide-react"
import { ConnectorLogo } from "@/components/connector-logo"
import { Button } from "@/components/ui/button"
import {
  disconnectConnector,
  getConnectorStatus,
  getGoogleAuthorizeUrl,
  triggerBackfill,
  type BackendSourceType,
} from "@/lib/api/connectors"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
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
 * (`backend/app/api/v1/connectors.py:81`). So the tiles report what the API
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
    enabled: Boolean(token) && canRead,
    retry: false,
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

  const started = Boolean(status.data?.cursor)
  const watching = Boolean(status.data?.watch_active)

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
            {!canRead
              ? "Needs connectors.read"
              : status.isPending
                ? "Checking…"
                : started
                  ? "Connected"
                  : "Not connected"}
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <StatTile
          label="Ingestion"
          value={started ? "Started" : "Not started"}
          on={started}
        />
        <StatTile
          label="Live updates"
          value={watching ? "On" : "Off"}
          on={watching}
        />
      </div>

      {canWrite && !status.error && (
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

export function ConnectorCard({
  connector,
  index,
}: {
  connector: ConnectorMeta
  index: number
}) {
  const token = useAuthStore((s) => s.accessToken)
  const canWrite = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.CONNECTORS_WRITE)
  )

  const authorize = useMutation({
    mutationFn: () => getGoogleAuthorizeUrl(token!),
    onSuccess: (data) => {
      if (data.authorization_url) window.location.href = data.authorization_url
    },
  })

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
          {GOOGLE_SOURCES.map((source) => (
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
          {connector.handshake} · {connector.cadence}
        </p>
        {live ? (
          canWrite && (
            <Button
              size="sm"
              disabled={authorize.isPending}
              onClick={() => authorize.mutate()}
            >
              <Plug className="size-3.5" />
              {authorize.isPending ? "Opening…" : "Connect"}
            </Button>
          )
        ) : (
          <Button size="sm" variant="outline" disabled>
            <Plug className="size-3.5" />
            Connect
          </Button>
        )}
      </div>

      {authorize.error && (
        <p role="alert" className="text-[0.8125rem] text-destructive">
          {authorize.error instanceof ApiError
            ? authorize.error.message
            : "Couldn't start the Google consent flow."}
        </p>
      )}
    </motion.li>
  )
}
