"use client"

import { motion, useReducedMotion } from "motion/react"
import { cn } from "@/lib/utils"

/**
 * The haze — the entire brand expression.
 *
 * Two very large, very soft ellipses bleeding down from the top of a white
 * page: saffron across the crown, periwinkle beneath it, dissolving to white
 * by the fold. It has to be *big* and *blurred*; the same colours applied to
 * borders, small marks or lattice geometry read as ethnic ornament rather
 * than as light, which is the trap the earlier version fell into.
 */
export function Haze({
  className,
  height = 900,
  intensity = 1,
}: {
  className?: string
  /** Vertical extent of the wash in px. */
  height?: number
  /** 0–1 multiplier, for sections that want a whisper of it. */
  intensity?: number
}) {
  const reduce = useReducedMotion()

  // Long, offset, non-repeating-looking drifts. Light that sits perfectly
  // still reads as a JPEG; these periods are slow enough (30–46s) that the
  // movement registers as atmosphere rather than as an animation.
  const layers = [
    {
      // Peak sits high so colour reaches the very top of the page. Pushing it
      // down left a dead white band above the wash.
      top: -120,
      h: 560,
      w: "135vw",
      blur: 110,
      opacity: 0.62,
      color: "var(--haze-saffron)",
      drift: { x: [0, 34, -22, 0], y: [0, -16, 12, 0] },
      duration: 34,
    },
    {
      top: 20,
      h: 640,
      w: "155vw",
      blur: 120,
      opacity: 0.5,
      color: "var(--haze-periwinkle)",
      drift: { x: [0, -40, 26, 0], y: [0, 18, -10, 0] },
      duration: 46,
    },
    {
      top: 300,
      h: 420,
      w: "110vw",
      blur: 100,
      opacity: 0.32,
      color: "var(--haze-violet)",
      drift: { x: [0, 26, -30, 0], y: [0, -12, 16, 0] },
      duration: 39,
    },
  ]

  return (
    <div
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-x-0 top-0 -z-10 overflow-hidden",
        className
      )}
      style={{ height }}
    >
      {layers.map((l, i) => (
        <motion.div
          key={i}
          className="absolute left-1/2 -translate-x-1/2 rounded-[50%]"
          style={{
            top: l.top,
            height: l.h,
            width: l.w,
            filter: `blur(${l.blur}px)`,
            opacity: l.opacity * intensity,
            background: `radial-gradient(ellipse at center, ${l.color}, transparent 68%)`,
          }}
          animate={reduce ? undefined : l.drift}
          transition={{
            duration: l.duration,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  )
}
