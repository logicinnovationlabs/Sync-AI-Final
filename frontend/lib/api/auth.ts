import { apiFetch } from "@/lib/api/client"

export interface LoginPayload {
  email: string
  password: string
  tenant_subdomain: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export function login(payload: LoginPayload) {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: payload,
  })
}

export interface RegisterPayload {
  tenant_subdomain: string
  email: string
  password: string
  display_name: string
}

export interface RegisterResponse {
  principal_id: string
  email: string
  display_name: string
  tenant_id: string
  auth_type: string
}

/**
 * Creates a native email/password user inside an existing tenant.
 *
 * ⚠️ This is `POST /api/v1/admin/users`, which the backend documents as
 * "(admin use)" but ships with **no auth dependency at all** — see
 * `backend/app/api/v1/admin.py:114`. It is the only endpoint that can create a
 * user, so self-serve signup goes through it, but the route needs a scope guard
 * before this is exposed publicly. Same applies to `POST /admin/tenants`.
 *
 * The tenant must already exist; an unknown subdomain comes back as a 404 with
 * `detail: "Tenant not found: …"`, which is surfaced to the user as-is.
 */
export function register(payload: RegisterPayload) {
  return apiFetch<RegisterResponse>("/admin/users", {
    method: "POST",
    body: payload,
  })
}

export interface ChangePasswordPayload {
  old_password: string
  new_password: string
}

export function changePassword(token: string, payload: ChangePasswordPayload) {
  return apiFetch<{ message: string }>("/me/change-password", {
    method: "POST",
    token,
    body: payload,
  })
}

export interface MeResponse {
  principal_id: string
  tenant_id: string
  scopes: string[]
  iat: number
  exp: number
}

export function getMe(token: string) {
  return apiFetch<MeResponse>("/me", { token })
}
