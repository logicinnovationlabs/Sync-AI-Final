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
 * Admin-vs-member follows JWT scopes from the persisted org role.
 * Members now also get connectors.read/write for their own Google account.
 * Do not treat connectors.write as admin.
 */
export function isAdmin(scopes: string[]): boolean {
  return scopes.some((scope) => scope.startsWith("admin."))
}
