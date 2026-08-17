import { apiFetch } from "@/lib/api/client"

export interface FederatedResultItem {
  document_id: string
  score: number
  title: string
  snippet: string
  sources: string[]
}

export interface FederatedSearchResponse {
  results: FederatedResultItem[]
  total: number
  took_ms: number
  degraded: boolean
  backends: Array<{
    name: string
    ok: boolean
    latency_ms: number
    error?: string | null
    hit_count: number
  }>
  query?: string | null
}

/** POST /api/v1/search/federated — Block J. Live path, not contracts.yaml `/api/v1/search`. */
export function federatedSearch(token: string, query: string) {
  return apiFetch<FederatedSearchResponse>("/search/federated", {
    method: "POST",
    token,
    body: {
      query,
      size: 20,
      enable_lexical: true,
      enable_vector: true,
    },
  })
}

export interface DocumentPayload {
  doc_id?: string
  document_id?: string
  tenant_id?: string
  body?: string
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

/** GET /api/v1/document/{doc_id} — Block K. Live path, not contracts.yaml POST `/api/v1/read`. */
export function getDocument(token: string, docId: string) {
  return apiFetch<DocumentPayload>(`/document/${encodeURIComponent(docId)}`, {
    token,
  })
}
