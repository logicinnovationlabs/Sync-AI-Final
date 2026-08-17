"use client"

import { useMemo, useState } from "react"
import { Search } from "lucide-react"
import { ConnectorLogo } from "@/components/connector-logo"
import { DocumentUpload } from "@/components/documents/document-upload"
import { CONNECTORS, type ConnectorSourceType } from "@/lib/connectors"
import { DEMO_ANSWERS } from "@/lib/demo-answers"
import { cn } from "@/lib/utils"

/**
 * The document browser.
 *
 * There is no documents or search endpoint on the backend — `app/main.py` mounts
 * auth, oauth, me, admin, connectors and webhooks. So the rows are the retrieved
 * records from `DEMO_ANSWERS`, deduplicated: the same scripted material the chat
 * surface and the landing page cite. The filtering and search are real and run
 * over that set; only the source of the rows is stubbed, and the surface says so
 * rather than implying an index exists.
 *
 * A beui `Table` was tried here for the bounded, virtualised viewport and
 * rejected on sight — sortable columns turned a set of records you *read* into
 * a spreadsheet you *operate*. Back to cards. Paging, not an inner scrollport,
 * is the answer to an index that grows; that lands with the endpoint.
 */

type Row = {
  id: string
  source: ConnectorSourceType
  title: string
  snippet: string
  meta: string
}

const ROWS: Row[] = Array.from(
  new Map(
    DEMO_ANSWERS.flatMap((answer) =>
      answer.sources.map(
        (source) =>
          [
            `${source.source}:${source.title}`,
            {
              id: `${source.source}:${source.title}`,
              source: source.source,
              title: source.title,
              snippet: source.snippet,
              meta: source.meta,
            },
          ] as const
      )
    )
  ).values()
)

export function DocumentBrowser() {
  const [query, setQuery] = useState("")
  const [source, setSource] = useState<ConnectorSourceType | "all">("all")

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return ROWS.filter((row) => {
      if (source !== "all" && row.source !== source) return false
      if (!q) return true
      return (
        row.title.toLowerCase().includes(q) ||
        row.snippet.toLowerCase().includes(q) ||
        row.meta.toLowerCase().includes(q)
      )
    })
  }, [query, source])

  // Only offer filters for sources that actually appear in the set.
  const present = useMemo(
    () => CONNECTORS.filter((c) => ROWS.some((r) => r.source === c.source)),
    []
  )

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-6 py-8">
      <DocumentUpload />

      <hr className="border-border-subtle" />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-muted-foreground" />
          <label htmlFor="doc-search" className="sr-only">
            Search indexed records
          </label>
          <input
            id="doc-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search titles, snippets and references…"
            className="h-11 w-full rounded-full border border-border bg-card pr-4 pl-11 text-sm outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-foreground/25 focus:ring-2 focus:ring-ring/40"
          />
        </div>

        <div role="group" aria-label="Filter by source" className="flex gap-1.5">
          <FilterChip active={source === "all"} onClick={() => setSource("all")}>
            All
          </FilterChip>
          {present.map((connector) => (
            <FilterChip
              key={connector.source}
              active={source === connector.source}
              onClick={() => setSource(connector.source)}
            >
              <ConnectorLogo source={connector.source} bare className="size-3.5" />
              {connector.shortLabel}
            </FilterChip>
          ))}
        </div>
      </div>

      <p className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
        {rows.length} {rows.length === 1 ? "record" : "records"}
      </p>

      {rows.length === 0 ? (
        <p className="rounded-[1.5rem] border border-dashed border-border px-6 py-16 text-center text-sm text-muted-foreground">
          Nothing matches “{query}”.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex items-start gap-3.5 rounded-[1.25rem] border border-border-subtle bg-card p-4 transition-colors duration-150 hover:border-border"
            >
              <ConnectorLogo source={row.source} className="size-8 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[0.875rem] font-medium">
                  {row.title}
                </p>
                <p className="mt-1 line-clamp-2 text-[0.8125rem] leading-relaxed text-muted-foreground">
                  {row.snippet}
                </p>
              </div>
              <p className="hidden shrink-0 font-mono text-[0.6875rem] text-muted-foreground sm:block">
                {row.meta}
              </p>
            </li>
          ))}
        </ul>
      )}

      <p className="text-center text-[0.6875rem] text-muted-foreground">
        Scripted demo records — the documents index isn&apos;t built yet.
      </p>
    </div>
  )
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.8125rem] transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        active
          ? "border-transparent bg-primary text-primary-foreground"
          : "border-border-subtle text-muted-foreground hover:border-border hover:text-foreground"
      )}
    >
      {children}
    </button>
  )
}
