import { decodeJwt } from "jose"

/**
 * Claims on SynQ's RS256 access token. Decoded client-side for display/
 * scope-gating only — this is NOT signature verification. Real
 * enforcement happens server-side on every API request.
 */
export interface AccessTokenClaims {
  sub: string
  tenant_id: string
  scopes: string[]
  iat: number
  exp: number
  role?: string
  must_change_password?: boolean
}

export function decodeAccessToken(token: string): AccessTokenClaims | null {
  try {
    return decodeJwt(token) as unknown as AccessTokenClaims
  } catch {
    return null
  }
}

export function isExpired(claims: { exp: number }): boolean {
  return Date.now() >= claims.exp * 1000
}
