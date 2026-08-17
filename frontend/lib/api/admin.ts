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

export function listAuditLogs(token: string) {
  return apiFetch<AuditLogPage>("/admin/audit?page=1&page_size=20", { token })
}
