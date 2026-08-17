import { SCOPES } from "@/lib/auth/scopes"

/**
 * Local-dev-only escape hatch: the backend has no code path today that
 * issues an admin-scoped JWT (native login hardcodes member scopes), so
 * the admin console can't be exercised end-to-end against a real session
 * yet. This lets development toggle a simulated admin session client-side
 * so the admin UI can be built and reviewed ahead of that backend work.
 * Must never run in production.
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
