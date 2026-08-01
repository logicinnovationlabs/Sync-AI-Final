const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"

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
  const { token, body, headers, ...rest } = options

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let message = res.statusText
    try {
      const data = await res.json()
      message = data.detail ?? data.error?.message ?? message
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
