"use client"

import { motion } from "motion/react"
import { SPRING_PRESS } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * An inline citation mark.
 *
 * Deliberately not a <sup>. Superscript pushed the mark onto a raised baseline
 * and stranded trailing ones alone on the next line; this is a baseline-aligned
 * chip that sits in the text rather than above it.
 *
 * It is a real <button> so the answer↔source link is reachable by keyboard, not
 * only by pointer. Shared with /chat when that surface lands.
 */
export function CiteMark({
  n,
  active = false,
  onActivate,
  onDeactivate,
  className,
}: {
  n: number
  /** Highlighted because its source card is being hovered or focused. */
  active?: boolean
  onActivate?: (n: number) => void
  onDeactivate?: () => void
  className?: string
}) {
  return (
    <motion.button
      type="button"
      initial={{ scale: 0.4, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={SPRING_PRESS}
      onMouseEnter={() => onActivate?.(n)}
      onMouseLeave={onDeactivate}
      onFocus={() => onActivate?.(n)}
      onBlur={onDeactivate}
      aria-label={`Source ${n}`}
      className={cn(
        "relative -top-px mx-px inline-flex h-[1.0625rem] min-w-[1.0625rem] cursor-pointer items-center justify-center rounded-[4px] px-1 align-baseline font-mono text-[0.625rem] font-semibold text-ink-blue transition-colors duration-200 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
        // text-background, not text-white: --ink-blue is dark on the light
        // theme and light on the dark one, so the label has to follow the
        // ground to stay legible in both.
        active
          ? "bg-ink-blue text-background"
          : "bg-ink-blue/12 hover:bg-ink-blue/25",
        className
      )}
    >
      {n}
    </motion.button>
  )
}
