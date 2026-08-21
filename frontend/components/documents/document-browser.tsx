"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"
import { DocumentUpload } from "@/components/documents/document-upload"
import { federatedSearch, getDocument } from "@/lib/api/search"
import { ApiError } from "@/lib/api/client"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { hasScope, SCOPES } from "@/lib/auth/scopes"

export function DocumentBrowser() {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const authenticated = useAuthStore((s) => s.isAuthenticated())
  const canSearch = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.SEARCH_READ)
  )
  const canReadDoc = useAuthStore((s) =>
    hasScope(s.effectiveScopes(), SCOPES.DOCUMENT_READ)
  )
  const [query, setQuery] = useState("")
  const [submitted, setSubmitted] = useState("*")
  const [openId, setOpenId] = useState<string | null>(null)

  const search = useQuery({
    queryKey: ["federated-search", submitted],
    queryFn: () => federatedSearch(token!, submitted || "*"),
    enabled: Boolean(token) && canSearch && submitted.length > 0,
    retry: false,
  })

  const document = useQuery({
    queryKey: ["document", openId],
    queryFn: () => getDocument(token!, openId!),
    enabled: Boolean(token) && canReadDoc && Boolean(openId),
    retry: false,
  })

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <DocumentUpload />

      <form
        onSubmit={(event) => {
          event.preventDefault()
          setSubmitted(query.trim() || "*")
          setOpenId(null)
        }}
        className="relative"
      >
        <Search className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
        <label htmlFor="doc-search" className="sr-only">
          Search indexed records
        </label>
        <input
          id="doc-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search indexed Drive, Gmail, and files — or press Enter to list them"
          className="h-11 w-full rounded-full border border-border bg-card pr-4 pl-11 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-foreground/25 focus:ring-2 focus:ring-ring/40"
        />
      </form>

      {hydrated && !authenticated && (
        <p className="text-sm text-muted-foreground">
          Sign in to search Block J (POST /search/federated).
        </p>
      )}
      {hydrated && authenticated && !canSearch && (
        <p className="text-sm text-destructive">
          This session is missing search.read — federated search will 403.
        </p>
      )}

      {search.isFetching && (
        <p className="text-sm text-muted-foreground">Searching…</p>
      )}
      {search.error && (
        <p role="alert" className="text-sm text-destructive">
          {search.error instanceof ApiError
            ? search.error.message
            : "Search failed"}
        </p>
      )}

      {search.data && (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            {search.data.total} result{search.data.total === 1 ? "" : "s"} ·{" "}
            {Math.round(search.data.took_ms)} ms
            {search.data.degraded ? " · degraded" : ""}
          </p>
          {search.data.results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No indexed hits.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {search.data.results.map((row) => (
                <li key={row.document_id}>
                  <button
                    type="button"
                    onClick={() =>
                      setOpenId(
                        openId === row.document_id ? null : row.document_id
                      )
                    }
                    className="w-full rounded-[1.25rem] border border-border-subtle bg-card p-4 text-left hover:border-border"
                  >
                    <p className="text-sm font-medium">
                      {row.title || row.document_id}
                    </p>
                    <p className="mt-1 line-clamp-2 text-[0.8125rem] text-muted-foreground">
                      {row.snippet}
                    </p>
                    <p className="mt-2 font-mono text-[0.625rem] text-muted-foreground">
                      {row.document_id} · score {row.score.toFixed(3)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {openId && (
        <div className="rounded-[1.25rem] border border-border bg-card p-4">
          <p className="text-xs font-medium text-muted-foreground">
            GET /document/{openId}
          </p>
          {document.isFetching && (
            <p className="mt-2 text-sm text-muted-foreground">Loading…</p>
          )}
          {document.error && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {document.error instanceof ApiError
                ? document.error.message
                : "Document read failed"}
            </p>
          )}
          {document.data && (
            <pre className="mt-3 max-h-80 overflow-auto text-[0.75rem] leading-relaxed">
              {typeof document.data.body === "string"
                ? document.data.body
                : JSON.stringify(document.data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
