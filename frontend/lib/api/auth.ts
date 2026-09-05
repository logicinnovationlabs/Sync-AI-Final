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
  role?: string
  must_change_password?: boolean
}

export function login(payload: LoginPayload) {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipAuthRefresh: true,
  })
}

/** Mint a new access token. Must not send the expired access JWT. */
export function refreshSession(refreshToken: string) {
  return apiFetch<LoginResponse>("/auth/refresh", {
    method: "POST",
    body: { refresh_token: refreshToken },
    skipAuthRefresh: true,
  })
}

/**
 * Self-serve signup is not a Block A/N contract.
 *
 * On suhani, `POST /admin/users` accepted `{ tenant_subdomain, email,
 * password, display_name }` with no auth. On Pratham, that route is
 * `Depends(require_admin)` and the body is `{ email, display_name, role? }`
 * with a server-generated temporary password. Calling the old shape would
 * 401/403 (or create the wrong kind of user if a leftover unauthenticated
 * path existed). Do not call this from the register page.
 */

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
  role?: string | null
  must_change_password?: boolean
  iat: number
  exp: number
}

export function getMe(token: string) {
  return apiFetch<MeResponse>("/me", { token, skipAuthRefresh: true })
}
