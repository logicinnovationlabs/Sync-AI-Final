import { cn } from "@/lib/utils"

/**
 * Wordmark-led, like the references. The previous gradient-tile monogram made
 * the ramp appear at 24px, where it stops reading as light and starts reading
 * as decoration — the haze is where colour lives now, so the mark stays quiet.
 */

const SIZE = {
  sm: "text-[1.0625rem]",
  md: "text-[1.25rem]",
  lg: "text-[1.625rem]",
} as const

const MARK_SIZE = {
  sm: "size-5",
  md: "size-6",
  lg: "size-8",
} as const

export function LogoMark({
  className,
  size = "md",
}: {
  className?: string
  size?: keyof typeof MARK_SIZE
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={cn("shrink-0 text-foreground", MARK_SIZE[size], className)}
    >
      {/* Concentric apertures — an opening, drawn geometrically. */}
      <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="12" cy="12" r="5.4" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
    </svg>
  )
}

export function Logo({
  className,
  size = "md",
  markOnly = false,
}: {
  className?: string
  size?: keyof typeof SIZE
  markOnly?: boolean
}) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark size={size} />
      {!markOnly && (
        <span
          className={cn(
            "font-heading leading-none font-medium tracking-[-0.015em]",
            SIZE[size]
          )}
        >
          SynQ AI
        </span>
      )}
    </span>
  )
}
