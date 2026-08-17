"use client"

import { motion } from "motion/react"
import { ConnectorLogo } from "@/components/connector-logo"
import type { ConnectorSourceType } from "@/lib/connectors"
import { SPRING_PRESS } from "@/lib/ease"
import { cn } from "@/lib/utils"

export type SourceCardData = {
  n: number
  source?: ConnectorSourceType
  title: string
  snippet: string
  meta: string
}

/**
 * A retrieved record, in the sources rail.
 *
 * Same visual language as the marketing demo's margin cards — deliberately, so
 * the thing you were shown on the landing page is the thing you get inside the
 * product. Hovering or focusing it lights the matching citation in the answer,
 * and the citation lights it back.
 */
export function SourceCard({
  source,
  active,
  onActivate,
  onDeactivate,
}: {
  source: SourceCardData
  active: boolean
  onActivate: (n: number) => void
  onDeactivate: () => void
}) {
  return (
    <motion.button
      type="button"
      onMouseEnter={() => onActivate(source.n)}
      onMouseLeave={onDeactivate}
      onFocus={() => onActivate(source.n)}
      onBlur={onDeactivate}
      animate={{ y: active ? -2 : 0 }}
      transition={SPRING_PRESS}
      whileTap={{ scale: 0.985 }}
      className={cn(
        "w-full cursor-pointer rounded-[1rem] border bg-card p-3.5 text-left transition-colors duration-150 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        active
          ? "border-ink-blue/45 shadow-[0_8px_28px_-12px_oklch(0.3_0.04_275/0.28)]"
          : "border-border-subtle hover:border-border"
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex size-[1.0625rem] shrink-0 items-center justify-center rounded-[4px] font-mono text-[0.625rem] font-semibold transition-colors duration-150",
            active ? "bg-ink-blue text-background" : "bg-ink-blue/12 text-ink-blue"
          )}
        >
          {source.n}
        </span>
        {source.source ? (
          <ConnectorLogo source={source.source} bare className="size-3.5" />
        ) : null}
        <span className="min-w-0 flex-1 truncate text-[0.8125rem] font-medium">
          {source.title}
        </span>
      </div>
      <p className="mt-1.5 line-clamp-2 text-[0.75rem] leading-relaxed text-muted-foreground">
        {source.snippet}
      </p>
      <p className="mt-1.5 font-mono text-[0.625rem] text-muted-foreground">
        {source.meta}
      </p>
    </motion.button>
  )
}
