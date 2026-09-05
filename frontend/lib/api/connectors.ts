import { apiFetch } from "@/lib/api/client"

/**
 * Connect HTTP lives on the connector tree (`backend/app/connectors/router.py`)
 * at `/connectors/...`. Guarded with `require_scope`.
 * Google Workspace is two source types, `google_drive` and `google_gmail`.
 */

export type BackendSourceType = "google_drive" | "google_gmail" | "sharepoint"

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

export function getConnectorStatus(token: string, source: BackendSourceType, connectionScope?: string) {
  const scope = connectionScope || "personal"
  return apiFetch<ConnectorStatus>(`/api/v1/connectors/${source}/status?connection_scope=${scope}`, { token })
}

export interface BackfillResponse {
  status: string
  task_id: string
  tenant_id: string
  source_type: string
}

export function triggerBackfill(token: string, source: BackendSourceType) {
  return apiFetch<BackfillResponse>(`/api/v1/connectors/${source}/backfill`, {
    method: "POST",
    token,
    body: { source_type: source },
  })
}

export function triggerOrganizationBackfill(token: string, source: BackendSourceType) {
  return apiFetch<BackfillResponse>(`/api/v1/connectors/admin/google/organization/${source}/backfill`, {
    method: "POST",
    token,
  })
}

export function disconnectConnector(token: string, source: BackendSourceType) {
  return apiFetch<{ status: string; tenant_id: string; source_type: string }>(
    `/api/v1/connectors/${source}/disconnect`,
    { method: "POST", token }
  )
}

export interface GoogleAuthorizeResponse {
  authorization_url: string
  tenant_id: string
  connection_scope: string
}

/**
 * Calls the authorize endpoint via XHR (with JWT) to get the Google OAuth URL.
 * The endpoint sets the oauth_binding cookie on the response for security.
 */
export function getGoogleAuthorizeUrl(token: string, connectionScope = "personal") {
  const endpoint = connectionScope === "organization"
    ? "/api/v1/connectors/google/authorize/organization"
    : "/api/v1/connectors/google/authorize"
  return apiFetch<GoogleAuthorizeResponse>(endpoint, {
    token,
  })
}

export interface OrganizationConnectRequest {
  vault_key: string
  impersonate_email: string
}

export interface OrganizationConnectResponse {
  status: string
  tenant_id: string
  vault_key: string
}

export function connectOrganizationConnector(token: string, request: OrganizationConnectRequest) {
  return apiFetch<OrganizationConnectResponse>("/api/v1/connectors/admin/google/organization/connect", {
    method: "POST",
    token,
    body: request,
  })
}

export function disconnectOrganizationConnector(token: string) {
  return apiFetch<{ status: string; tenant_id: string }>(
    "/api/v1/connectors/admin/google/organization/disconnect",
    { method: "POST", token }
  )
}

export interface OrganizationToggleRequest {
  enabled: boolean
}

export interface OrganizationToggleResponse {
  status: string
  tenant_id: string
  enabled: boolean
}

export function toggleOrganizationConnector(token: string, request: OrganizationToggleRequest) {
  return apiFetch<OrganizationToggleResponse>("/api/v1/connectors/admin/google/organization/toggle", {
    method: "POST",
    token,
    body: request,
  })
}

export function getOrganizationConnectorStatus(token: string, sourceType: BackendSourceType) {
  if (sourceType === "sharepoint") {
    return apiFetch<ConnectorStatus>("/api/v1/connectors/sharepoint/organization/status", {
      token,
    })
  }
  return apiFetch<ConnectorStatus>(`/api/v1/connectors/google/organization/status?source_type=${sourceType}`, {
    token,
  })
}

export interface SharePointConnectRequest {
  vault_key: string
  site_url?: string
}

export function connectSharePointOrganization(token: string, request: SharePointConnectRequest) {
  return apiFetch<OrganizationConnectResponse>("/api/v1/connectors/admin/sharepoint/organization/connect", {
    method: "POST",
    token,
    body: request,
  })
}

export function disconnectSharePointOrganization(token: string) {
  return apiFetch<{ status: string; tenant_id: string }>(
    "/api/v1/connectors/admin/sharepoint/organization/disconnect",
    { method: "POST", token }
  )
}

export function toggleSharePointOrganization(token: string, request: OrganizationToggleRequest) {
  return apiFetch<OrganizationToggleResponse>("/api/v1/connectors/admin/sharepoint/organization/toggle", {
    method: "POST",
    token,
    body: request,
  })
}

export function triggerSharePointOrganizationBackfill(token: string) {
  return apiFetch<BackfillResponse>("/api/v1/connectors/admin/sharepoint/organization/backfill", {
    method: "POST",
    token,
  })
}

export function getSharePointAuthorizeUrl(token: string) {
  return apiFetch<GoogleAuthorizeResponse>("/api/v1/connectors/sharepoint/authorize", {
    token,
  })
}
