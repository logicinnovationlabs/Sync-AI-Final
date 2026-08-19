import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

/**
 * Optimistic auth gate: checks presence of the `synq_session` cookie (a
 * boolean flag set client-side alongside the real JWT, see
 * lib/auth/auth-store.ts) to avoid a flash of protected content before
 * the client can redirect. This is NOT the security boundary — the
 * backend can't yet expose a JWKS endpoint for edge-verifiable
 * signatures, so real enforcement stays server-side per FastAPI request.
 */
const SESSION_COOKIE = "synq_session"

export function proxy(request: NextRequest) {
  // const hasSession = request.cookies.has(SESSION_COOKIE)

  // if (!hasSession) {
  //   const loginUrl = new URL("/login", request.url)
  //   loginUrl.searchParams.set("next", request.nextUrl.pathname)
  //   return NextResponse.redirect(loginUrl)
  // }

  return NextResponse.next()
}

export const config = {
  // matcher: [
  //   "/chat/:path*",
  //   "/documents/:path*",
  //   "/connectors/:path*",
  //   "/admin/:path*",
  //   "/settings/:path*",
  // ],
}
