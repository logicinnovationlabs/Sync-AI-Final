import { apiFetch } from "@/lib/api/client"

/**
 * Connect HTTP lives on the connector tree (`backend/app/connectors/router.py`)
 * at `/connectors/...`. Guarded with `require_scope`.
 * Google Workspace is two source types, `google_drive` and `google_gmail`.
 */

export type BackendSourceType = "google_drive" | "google_gmail"

export interface ConnectorStatus {
  tenant_id: string
  source_type: string
  /** Sync cursor. Null or empty means nothing has been ingested yet. */
  cursor: string | null
  watch_active: boolean
  details: {
    connection_status?: "not_connected" | "syncing" | "active" | "error" | "needs_reauth"
    files_indexed?: number
    last_sync_at?: string | null
    last_error?: string | null
    token_present?: boolean
    watch_info?: Record<string, unknown>
  } & Record<string, unknown>
}

export function getConnectorStatus(token: string, source: BackendSourceType) {
  return apiFetch<ConnectorStatus>(`/connectors/${source}/status`, { token })
}

export interface BackfillResponse {
  status: string
  task_id: string
  tenant_id: string
  source_type: string
}

export function triggerBackfill(token: string, source: BackendSourceType) {
  return apiFetch<BackfillResponse>(`/connectors/${source}/backfill`, {
    method: "POST",
    token,
    body: { source_type: source },
  })
}

export function disconnectConnector(token: string, source: BackendSourceType) {
  return apiFetch<{ status: string; tenant_id: string; source_type: string }>(
    `/connectors/${source}/disconnect`,
    { method: "POST", token }
  )
}

export interface GoogleAuthorizeResponse {
  authorization_url: string
  tenant_id: string
}

export function getGoogleAuthorizeUrl(token: string) {
  return apiFetch<GoogleAuthorizeResponse>("/connectors/google/authorize", {
    token,
  })
}
