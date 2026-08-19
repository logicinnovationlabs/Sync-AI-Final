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
 * Admin-vs-member follows JWT scopes issued from the persisted org role
 * (Block N `scopes_for_role`). An admin login includes `connectors.write`
 * and `admin.*`. Members only get search.read + document.read.
 */
export function isAdmin(scopes: string[]): boolean {
  return (
    hasScope(scopes, SCOPES.CONNECTORS_WRITE) ||
    scopes.some((scope) => scope.startsWith("admin."))
  )
}
