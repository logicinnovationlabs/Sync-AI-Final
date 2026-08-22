import { decodeAccessToken, isExpired } from "@/lib/auth/jwt"
import { useAuthStore } from "@/lib/auth/auth-store"

function normalizeApiBase(raw: string): string {
  return raw.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "")
}

const API_BASE_URL = normalizeApiBase(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
)

/** Refresh 30s before exp so Connectors /status never sends a dead JWT. */
const ACCESS_SKEW_MS = 30_000

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

interface ApiFetchOptions extends Omit<RequestInit, "body"> {
  token?: string | null
  body?: unknown
  /** Skip refresh (login / refresh itself). */
  skipAuthRefresh?: boolean
}

let refreshInFlight: Promise<string | null> | null = null

async function exchangeRefreshToken(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const { refreshToken, email } = useAuthStore.getState()
    if (!refreshToken) return null
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) {
      useAuthStore.getState().clearSession()
      return null
    }
    const data = (await res.json()) as {
      access_token?: string
      refresh_token?: string
    }
    if (!data.access_token || !data.refresh_token) {
      useAuthStore.getState().clearSession()
      return null
    }
    useAuthStore.getState().setSession({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      email: email ?? "",
    })
    return data.access_token
  })().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

async function resolveAccessToken(passed: string | null | undefined): Promise<string | null> {
  const store = useAuthStore.getState()
  const candidate = store.accessToken || passed || null
  if (!candidate) return passed ?? null
  const claims = decodeAccessToken(candidate)
  if (claims && !isExpired(claims, ACCESS_SKEW_MS)) return candidate
  if (!store.refreshToken) return candidate
  return (await exchangeRefreshToken()) ?? candidate
}

/**
 * Thin fetch wrapper against the SynQ FastAPI backend.
 * Backend error responses are plain `{ detail: string }` (FastAPI's
 * default HTTPException shape) — not the richer ErrorDetail envelope
 * defined in core/errors.py, which no route currently returns.
 */
export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { token, body, headers, skipAuthRefresh, ...rest } = options

  const access = skipAuthRefresh ? token ?? null : await resolveAccessToken(token)

  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${API_BASE_URL}. Check NEXT_PUBLIC_API_BASE_URL and backend CORS (FRONTEND_URL / CORS_ALLOWED_ORIGINS on Render).`
    )
  }

  if (!res.ok) {
    const expiredAccess =
      !skipAuthRefresh &&
      res.status === 401 &&
      Boolean(useAuthStore.getState().refreshToken)
    if (expiredAccess) {
      const renewed = await exchangeRefreshToken()
      if (renewed) {
        return apiFetch<T>(path, { ...options, token: renewed, skipAuthRefresh: true })
      }
    }
    let message = res.statusText
    try {
      const data = await res.json()
      message = formatApiError(data) ?? message
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, message)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return (await res.json()) as T
}

export { API_BASE_URL }

/** FastAPI `{ detail }` or the Block A error envelope `{ error: { message } }`. */
export function formatApiError(data: unknown): string | null {
  if (!data || typeof data !== "object") return null
  const body = data as {
    detail?: unknown
    error?: { message?: unknown }
  }
  if (typeof body.detail === "string" && body.detail) return body.detail
  if (Array.isArray(body.detail) && body.detail.length > 0) {
    const first = body.detail[0]
    if (typeof first === "string") return first
    if (first && typeof first === "object" && "msg" in first) {
      return String((first as { msg: unknown }).msg)
    }
    return JSON.stringify(body.detail)
  }
  if (typeof body.error?.message === "string" && body.error.message) {
    return body.error.message
  }
  return null
}
