import { API_BASE_URL, ApiError, apiFetch, formatApiError } from "@/lib/api/client"

export interface AssistantCitation {
  document_id?: string | null
  title?: string | null
  source_id?: string | null
  chunk_id?: string | null
  page?: string | number | null
  quote?: string | null
  score?: number | null
  base_score?: number | null
}

export type AssistantStreamEvent =
  | {
      type: "meta"
      intent?: string
      used_document_reader?: boolean
      latency_ms?: number
      timings_ms?: Record<string, number>
      chat_provider_name?: string
    }
  | { type: "token"; text: string }
  | {
      type: "final"
      response_text: string
      citations: AssistantCitation[]
      ranked_hits: Array<Record<string, unknown>>
      session_id: string
      tenant_id: string
      errors?: unknown[]
      chat_provider_name?: string
      timings_ms?: Record<string, number>
      generation_error?: string
      debug_retrieval?: Array<Record<string, unknown>>
    }

const CHAT_TIMEOUT_MS = 120_000

function assistantDebugEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_ASSISTANT_DEBUG === "1") return true
  if (process.env.NEXT_PUBLIC_ASSISTANT_DEBUG === "0") return false
  return process.env.NODE_ENV === "development"
}

function pipelineLog(stage: string, detail?: Record<string, unknown>) {
  const payload = detail ? { stage, ...detail } : { stage }
  console.info("[assistant.pipeline]", payload)
}

/**
 * POST /assistant/orchestrator/chat — Block L NDJSON stream.
 *
 * Tokens are only emitted after the backend Qwen generation completes.
 * The UI must not treat an in-flight buffer as a final answer.
 */
export async function streamAssistantChat(params: {
  token: string
  prompt: string
  sessionId: string
  tenantId?: string
  debug?: boolean
  signal?: AbortSignal
  onEvent: (event: AssistantStreamEvent) => void
}): Promise<void> {
  const debug = params.debug ?? assistantDebugEnabled()
  const t0 =
    typeof performance !== "undefined" ? performance.now() : Date.now()
  pipelineLog("request_sent", { prompt_len: params.prompt.length, debug })

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)
  const onExternalAbort = () => controller.abort()
  if (params.signal) {
    if (params.signal.aborted) controller.abort()
    else params.signal.addEventListener("abort", onExternalAbort, { once: true })
  }

  try {
    const res = await fetch(`${API_BASE_URL}/assistant/orchestrator/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${params.token}`,
      },
      body: JSON.stringify({
        prompt: params.prompt,
        session_id: params.sessionId,
        debug,
        ...(params.tenantId ? { tenant_id: params.tenantId } : {}),
      }),
      signal: controller.signal,
    })

    if (!res.ok) {
      let message = res.statusText
      try {
        message = formatApiError(await res.json()) ?? message
      } catch {
        // ignore
      }
      if (res.status === 405) {
        message =
          "Chat is POST-only. Refresh the page (a leftover service worker can turn this into GET)."
      }
      throw new ApiError(res.status, message)
    }

    if (!res.body) {
      throw new ApiError(res.status, "Chat response had no body")
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let sawToken = false
    let sawFinal = false

    const onAbort = () => {
      try {
        void reader.cancel()
      } catch {
        // ignore
      }
    }
    controller.signal.addEventListener("abort", onAbort, { once: true })

    const handleLine = (line: string) => {
      const trimmed = line.trim()
      if (!trimmed) return
      let event: AssistantStreamEvent
      try {
        event = JSON.parse(trimmed) as AssistantStreamEvent
      } catch {
        pipelineLog("malformed_ndjson_line")
        return
      }
      if (event.type === "token" && !sawToken) {
        sawToken = true
        pipelineLog("first_token_received", {
          elapsed_ms: Math.round(
            (typeof performance !== "undefined" ? performance.now() : Date.now()) - t0
          ),
        })
      }
      if (event.type === "meta") {
        pipelineLog("meta_received", {
          provider: event.chat_provider_name,
          latency_ms: event.latency_ms,
          timings_ms: event.timings_ms,
        })
      }
      if (event.type === "final") {
        sawFinal = true
        if (event.chat_provider_name === "fake") {
          console.warn(
            "[assistant.pipeline] chat_provider=fake — Qwen was not called. Set LLM_CHAT_PROVIDER=openrouter on the backend."
          )
        }
        if (debug && event.debug_retrieval) {
          pipelineLog("debug_retrieval", {
            chunks: event.debug_retrieval,
            timings_ms: event.timings_ms,
          })
        }
        pipelineLog("response_rendered", {
          elapsed_ms: Math.round(
            (typeof performance !== "undefined" ? performance.now() : Date.now()) - t0
          ),
          provider: event.chat_provider_name,
          generation_error: event.generation_error || undefined,
        })
      }
      params.onEvent(event)
    }

    try {
      while (true) {
        if (controller.signal.aborted || params.signal?.aborted) {
          break
        }
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          handleLine(line)
        }
      }
      if (buffer.trim()) {
        handleLine(buffer)
      }
    } catch (readErr) {
      if (controller.signal.aborted || params.signal?.aborted) {
        throw new DOMException("The operation was aborted.", "AbortError")
      }
      throw readErr
    }

    const wasAborted = controller.signal.aborted || Boolean(params.signal?.aborted)
    if (wasAborted) {
      throw new DOMException("The operation was aborted.", "AbortError")
    }

    if (!sawFinal) {
      throw new ApiError(502, "Incomplete assistant response (no final event).")
    }
  } finally {
    clearTimeout(timeoutId)
    if (params.signal) {
      params.signal.removeEventListener("abort", onExternalAbort)
    }
  }
}

export interface AssistantSessionSummary {
  session_id: string
  title: string
  turn_count: number
  updated_at?: string | null
}

export interface AssistantSessionTurn {
  role: string
  content: string
  citations?: AssistantCitation[]
}

export interface AssistantSessionDetail {
  session_id: string
  tenant_id: string
  user_id: string
  turn_count: number
  title?: string
  history: AssistantSessionTurn[]
}

export function listAssistantSessions(token: string) {
  return apiFetch<AssistantSessionSummary[]>("/assistant/orchestrator/sessions", {
    token,
  })
}

export function getAssistantSession(token: string, sessionId: string) {
  return apiFetch<AssistantSessionDetail>(
    `/assistant/orchestrator/sessions/${encodeURIComponent(sessionId)}`,
    { token }
  )
}

/** Strip model citation markup like `[5, 6]` / `[1, p.1]` from displayed prose while preserving markdown formatting. */
export function stripInlineCitations(text: string): string {
  if (!text) return ""
  return text
    .replace(/\s*\[\s*\d+(?:\s*,\s*(?:p\.\s*)?\d+)*\s*\]/gi, "")
    .trim()
}
