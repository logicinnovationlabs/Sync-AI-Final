export const SCOPES = {
  SEARCH_READ: "search.read",
  DOCUMENT_READ: "document.read",
  CONNECTORS_READ: "connectors.read",
  CONNECTORS_WRITE: "connectors.write",
  ADMIN_AUDIT_READ: "admin.audit.read",
} as const

export function hasScope(scopes: string[], scope: string): boolean {
  return scopes.includes(scope)
}

/**
 * Admin-vs-member is not a real field on the backend today — it's purely
 * derived from scopes. Native login currently always grants
 * ["search.read", "document.read"], so no login can produce an admin
 * session yet (see lib/auth/dev-overrides.ts for the local dev escape
 * hatch used to build/test the admin console ahead of that).
 */
export function isAdmin(scopes: string[]): boolean {
  return (
    hasScope(scopes, SCOPES.CONNECTORS_WRITE) ||
    scopes.some((scope) => scope.startsWith("admin."))
  )
}
