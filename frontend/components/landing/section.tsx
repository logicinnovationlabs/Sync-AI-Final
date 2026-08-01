"use client"

import { motion } from "motion/react"
import { EASE_OUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * One shell for every marketing section.
 *
 * Centred heading over a large white card, on white. Separation comes from
 * radius, a hairline and generous space — not from alternating grounds or
 * full-width rules, which chopped the page into six identical bands.
 */

export function SectionShell({
  id,
  children,
  className,
}: {
  id?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section id={id} className={cn("relative", className)}>
      <div className="mx-auto max-w-6xl px-6 py-16 lg:py-24">{children}</div>
    </section>
  )
}

export function SectionHead({
  eyebrow,
  heading,
  lead,
  align = "center",
}: {
  eyebrow?: string
  heading: React.ReactNode
  lead?: React.ReactNode
  align?: "center" | "left"
}) {
  // Eyebrow, heading and lead arrive in that order rather than all at once —
  // the stagger is what makes a section feel authored instead of painted.
  const rise = {
    hidden: { opacity: 0, y: 14 },
    show: { opacity: 1, y: 0 },
  }

  return (
    <motion.div
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.5 }}
      transition={{ staggerChildren: 0.08 }}
      className={cn(
        "flex flex-col gap-4",
        align === "center"
          ? "mx-auto max-w-3xl items-center text-center"
          : "max-w-2xl"
      )}
    >
      {eyebrow && (
        <motion.p
          variants={rise}
          transition={{ duration: 0.5, ease: EASE_OUT }}
          className="text-[0.875rem] font-medium text-ink-blue"
        >
          {eyebrow}
        </motion.p>
      )}
      <motion.h2
        variants={rise}
        transition={{ duration: 0.6, ease: EASE_OUT }}
        className="font-heading text-[clamp(2rem,3.8vw,3rem)] leading-[1.1] font-normal tracking-[-0.018em] text-balance"
      >
        {heading}
      </motion.h2>
      {lead && (
        <motion.p
          variants={rise}
          transition={{ duration: 0.6, ease: EASE_OUT }}
          className="max-w-[56ch] text-[1.0625rem] leading-relaxed text-muted-foreground text-pretty"
        >
          {lead}
        </motion.p>
      )}
    </motion.div>
  )
}

/** The big soft container everything sits in. */
export function Panel({
  children,
  className,
  padded = true,
}: {
  children: React.ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[1.75rem] border border-border-subtle bg-card shadow-[0_2px_40px_-12px_oklch(0.3_0.04_275/0.12)]",
        padded && "p-6 sm:p-9",
        className
      )}
    >
      {children}
    </div>
  )
}
