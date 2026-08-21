/**
 * Which tenant is this browser signing in to?
 *
 * `POST /auth/login` requires `tenant_subdomain` — `NativeLoginRequest` declares
 * it and the handler resolves the tenant by subdomain *before* it checks the
 * password (`backend/app/api/v1/auth.py:31,70`). The sign-in form no longer asks
 * for it, so it has to come from somewhere else.
 *
 * It comes from the hostname: `acme.synq.ai` → `acme`. That is what the backend
 * field has always implied, and it commits the product to subdomain-per-tenant
 * routing in production (wildcard DNS and certificate).
 *
 * Locally there is no subdomain to read — `localhost` and `127.0.0.1` have none
 * — so it falls back to `NEXT_PUBLIC_DEFAULT_TENANT`. Without that set, login
 * comes back 404 "Tenant not found", which is the honest failure: we genuinely
 * don't know which workspace you meant.
 *
 * Registration still asks for the workspace outright, because you pick which one
 * you're joining before you're inside it and there's no hostname to infer from.
 */

/** Hosts that never carry a tenant subdomain. */
const BARE_HOSTS = new Set(["localhost", "127.0.0.1", "0.0.0.0", "[::1]"])

/** Subdomains that are ours, not a tenant's. */
const RESERVED = new Set(["www", "app", "api", "admin", "staging", "preview"])

export function tenantFromHost(hostname?: string): string {
  const host = (hostname ?? (typeof window !== "undefined" ? window.location.hostname : ""))
    .toLowerCase()
    .replace(/:\d+$/, "")

  const fallback = (process.env.NEXT_PUBLIC_DEFAULT_TENANT || "alpha").trim()

  if (!host || BARE_HOSTS.has(host)) return fallback

  const labels = host.split(".")
  // Needs at least sub.domain.tld — `synq.ai` on its own is the marketing site.
  if (labels.length < 3) return fallback

  const sub = labels[0]
  if (!sub || RESERVED.has(sub)) return fallback

  return sub
}
