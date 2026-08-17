"use client"

import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useEffect, useState } from "react"

/**
 * The oversized wordmark that closes the page, filled with photography.
 *
 * The reference clips theirs to photographs and lets the word run off the
 * bottom edge of the page. Two earlier attempts here failed for reasons worth
 * recording:
 *
 *   1. Six unrelated gradients cycling every 3.8s. The failure was the
 *      *cycling* — a mark that changes identity every four seconds never
 *      becomes one.
 *   2. A single haze gradient. Better, but a gradient inside letterforms is
 *      just coloured text; it has no material.
 *
 * Now: four public-domain textile and block-print photographs, crossfading on a
 * slow clock. Same device as the reference, honest materials.
 *
 * ── No crop, and why ─────────────────────────────────────────────────────────
 * The reference crops theirs at the page edge, but "sarvam" is all-lowercase
 * with *zero descenders*, so a cut severs nothing. "SynQ AI" has a `y` tail and
 * a `Q` tail, and every crop depth tried here cost something:
 *
 *   · 0.20em cut *through* both tails and left stubs.
 *   · 0.34em cut *above* the baseline, removing the tails entirely — which
 *     turned the `y` into a `v` and the `Q` into an `O`. It read "SvnO AI".
 *   · 0.12em trimmed only the tips, which was legible but still a cut.
 *
 * So the word is now shown whole, and set smaller. It's a closing grace note,
 * not the loudest thing on the page — at full bleed it was competing with the
 * footer it was supposed to sit under.
 *
 * ── Provenance ───────────────────────────────────────────────────────────────
 * All four are **CC0 1.0 (public domain)** — no attribution required, cleared
 * for commercial use. Sourced via the Openverse index (api.openverse.org);
 * Unsplash and Pexels both refuse server-side fetches (401 / 403).
 *
 *   texture-01  rawpixel.com/image/7653477   CC0 1.0
 *   texture-02  wordpress.org/photos/photo/40168a5473  CC0 1.0  (Sunil Kumar Sharma)
 *   texture-03  rawpixel.com/image/7654210   CC0 1.0
 *   texture-04  rawpixel.com/image/9064449   CC0 1.0
 */

const WORD = "SynQ AI"

const TEXTURES = [
  "/brand/texture-01.webp", // saffron & gold block print
  "/brand/texture-02.webp", // deep red & gold
  "/brand/texture-03.webp", // indigo batik, light
  "/brand/texture-04.webp", // navy indigo & cream
]

// Long hold, slow dissolve. The old version flipped every 3.8s, which is what
// made it read as a gimmick rather than as a brand mark.
const HOLD_MS = 7000

// Measured: "SynQ AI" renders 3.376× its font size wide at this weight and
// tracking. 16vw lands it at ~54% of the viewport — present, but clearly
// decoration rather than the focus. Capped so it stops growing on an ultrawide.
const SIZE = "text-[clamp(2.5rem,16vw,11rem)]"
const TYPE = `block text-center font-heading ${SIZE} leading-[1.12] font-medium tracking-[-0.05em]`

export function FooterWordmark() {
  const reduce = useReducedMotion()
  const [i, setI] = useState(0)

  useEffect(() => {
    if (reduce) return
    const t = setInterval(() => setI((n) => (n + 1) % TEXTURES.length), HOLD_MS)
    return () => clearInterval(t)
  }, [reduce])

  return (
    <div
      aria-hidden
      className="pointer-events-none relative mt-10 w-full select-none"
    >
      <div className="relative px-6 pb-4">
        {/* Invisible copy sets the box; the filled layers stack on top of it.
            No negative margin any more — the descenders need the room. */}
        <span className={`${TYPE} invisible`}>{WORD}</span>

        <AnimatePresence mode="sync">
          <motion.span
            key={i}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.5, ease: "easeInOut" }}
            className={`${TYPE} absolute inset-x-6 top-0 bg-cover bg-center text-transparent`}
            style={{
              backgroundImage: `url(${TEXTURES[i]})`,
              WebkitBackgroundClip: "text",
              backgroundClip: "text",
            }}
          >
            {WORD}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  )
}
