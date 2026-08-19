import { SCOPES } from "@/lib/auth/scopes"

/**
 * Local-dev-only escape hatch. Prefer signing in as the seeded Alpha
 * admin (see lib/dev-login.ts). This override remains for UI work when
 * the backend is down. Must never run in production.
 */
const DEV_ADMIN_OVERRIDE_KEY = "synq_dev_admin_override"

export function isDevAdminOverrideEnabled(): boolean {
  if (process.env.NODE_ENV !== "development") return false
  if (typeof window === "undefined") return false
  return window.localStorage.getItem(DEV_ADMIN_OVERRIDE_KEY) === "1"
}

export function setDevAdminOverride(enabled: boolean): void {
  if (process.env.NODE_ENV !== "development") return
  if (typeof window === "undefined") return
  if (enabled) {
    window.localStorage.setItem(DEV_ADMIN_OVERRIDE_KEY, "1")
  } else {
    window.localStorage.removeItem(DEV_ADMIN_OVERRIDE_KEY)
  }
}

export const DEV_ADMIN_SCOPES: string[] = [
  SCOPES.SEARCH_READ,
  SCOPES.DOCUMENT_READ,
  SCOPES.CONNECTORS_READ,
  SCOPES.CONNECTORS_WRITE,
  SCOPES.ADMIN_AUDIT_READ,
]
