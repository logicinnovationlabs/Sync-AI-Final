import { apiFetch } from "@/lib/api/client"

/**
 * The connector endpoints are real — `backend/app/api/v1/connectors.py` mounts
 * all four and guards them with `require_scope`. Note the backend's notion of a
 * source is finer-grained than the UI's: Google Workspace is two source types,
 * `google_drive` and `google_gmail`, each with its own cursor and watch.
 */
export type BackendSourceType = "google_drive" | "google_gmail"

export interface ConnectorStatus {
  tenant_id: string
  source_type: string
  /** Sync cursor. Null or empty means nothing has been ingested yet. */
  cursor: string | null
  watch_active: boolean
  details: Record<string, unknown>
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
