import { API_BASE_URL, ApiError, formatApiError } from "@/lib/api/client"

export interface AssistantCitation {
  document_id?: string | null
  quote?: string | null
  score?: number | null
  base_score?: number | null
}

export type AssistantStreamEvent =
  | { type: "meta"; intent?: string; used_document_reader?: boolean; latency_ms?: number }
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
    }

/**
 * POST /api/v1/assistant/orchestrator/chat — Block L NDJSON stream.
 * Not the contracts.yaml path `/api/v1/assistant/chat`.
 */
export async function streamAssistantChat(params: {
  token: string
  prompt: string
  sessionId: string
  tenantId?: string
  onEvent: (event: AssistantStreamEvent) => void
}): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/assistant/orchestrator/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${params.token}`,
    },
    body: JSON.stringify({
      prompt: params.prompt,
      session_id: params.sessionId,
      ...(params.tenantId ? { tenant_id: params.tenantId } : {}),
    }),
  })

  if (!res.ok) {
    let message = res.statusText
    try {
      message = formatApiError(await res.json()) ?? message
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message)
  }

  if (!res.body) {
    throw new ApiError(res.status, "Chat response had no body")
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      params.onEvent(JSON.parse(trimmed) as AssistantStreamEvent)
    }
  }
  if (buffer.trim()) {
    params.onEvent(JSON.parse(buffer.trim()) as AssistantStreamEvent)
  }
}
