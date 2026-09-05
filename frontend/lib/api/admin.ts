import { apiFetch } from "@/lib/api/client"

export interface AdminUserItem {
  principal_id: string
  email: string
  display_name: string
  role: string
  is_active: boolean
  status: string
  must_change_password: boolean
  invited_by?: string | null
}

export interface AuditLogItem {
  id: string
  actor_id: string
  action_type: string
  target_json?: Record<string, unknown> | null
  ip_address?: string | null
  created_at: string
}

export interface AuditLogPage {
  items: AuditLogItem[]
  page: number
  page_size: number
  total: number
}

export function listAdminUsers(token: string) {
  return apiFetch<AdminUserItem[]>("/admin/users", { token })
}

export function patchAdminUser(token: string, userId: string, data: { role?: string; is_active?: boolean }) {
  return apiFetch<AdminUserItem>(`/admin/users/${userId}`, {
    token,
    method: "PATCH",
    body: data,
  })
}

export function deactivateAdminUser(token: string, userId: string) {
  return apiFetch<AdminUserItem>(`/admin/users/${userId}`, {
    token,
    method: "DELETE",
  })
}

export function transferOwnership(token: string, targetUserId: string) {
  return apiFetch<AdminUserItem>("/admin/users/transfer-ownership", {
    token,
    method: "POST",
    body: { target_user_id: targetUserId },
  })
}

export function listAuditLogs(token: string) {
  return apiFetch<AuditLogPage>("/api/v1/admin/audit?page=1&page_size=20", { token })
}

export interface PendingIdentityItem {
  document_id: string
  shared_email: string
  first_seen_at: string | null
}

export function listPendingIdentities(token: string) {
  return apiFetch<PendingIdentityItem[]>("/api/v1/admin/pending-identities", { token })
}

// Document Access Control (Part 2.2)
export interface MemberListItem {
  principal_id: string
  email: string
  display_name: string
  role: string
  is_active: boolean
  status: string
  document_count: number
  owned_count: number
  shared_count: number
  connector_connected: boolean
}

export interface DocumentListItem {
  document_id: string
  title: string
  source_type: string
  owner_principal_id: string | null
  created_at: string
  access_override: "allow" | "deny" | null
  assignment: "owned" | "shared"
}

export function listMembers(token: string) {
  return apiFetch<MemberListItem[]>("/admin/members", { token })
}

export function listMemberDocuments(token: string, userId: string) {
  return apiFetch<DocumentListItem[]>(`/admin/members/${userId}/documents`, { token })
}

export function setAccessOverride(token: string, userId: string, documentId: string, access: "allow" | "deny") {
  return apiFetch<{ message: string }>(`/admin/members/${userId}/documents/${documentId}/access`, {
    token,
    method: "POST",
    body: { access },
  })
}

export function removeAccessOverride(token: string, userId: string, documentId: string) {
  return apiFetch<{ message: string }>(`/admin/members/${userId}/documents/${documentId}/access`, {
    token,
    method: "DELETE",
  })
}
