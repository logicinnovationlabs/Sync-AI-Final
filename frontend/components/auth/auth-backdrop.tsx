"use client"

import { usePathname } from "next/navigation"
import {
  ShaderBackground,
  type ShaderBackgroundProps,
} from "@/components/motion/shader-background"

/**
 * The art half of the split auth shell.
 *
 * One shader per page, running continuously — no crossfading between variants.
 * Sign-in gets the flowing mesh; register gets the static "dusk" mesh, so the
 * two doors are recognisably the same family without being the same picture.
 *
 * Parameters are the library's own preset values (`meshGradientPresets`,
 * `staticMeshGradientPresets` in @paper-design/shaders-react) with only the
 * colours swapped for the project's haze. That is deliberate: every earlier
 * attempt to hand-tune this family produced an empty canvas — `color-panels`
 * below its density threshold, and `mesh-gradient` whenever `fit` was
 * overridden. The presets paint; leave the numbers alone.
 *
 * Colours are hex because the shader uploads them to WebGL and never sees the
 * stylesheet. They are the sRGB conversions of `--haze-*` in `app/globals.css`
 * and must be updated alongside those.
 *
 * `ShaderBackground` already forces `speed: 0` under `prefers-reduced-motion`.
 */

const SAFFRON = "#f0a35e"
const PERIWINKLE = "#a3b2fe"
const VIOLET = "#b39bf0"
const PAPER = "#f4f1fb"
const INK = "#2b2a45"

const MESH: ShaderBackgroundProps = {
  variant: "mesh-gradient",
  colors: [PAPER, SAFFRON, PERIWINKLE, VIOLET],
  distortion: 0.8,
  swirl: 0.1,
  grainMixer: 0,
  grainOverlay: 0,
  speed: 0.6,
}

const STATIC_MESH_DUSK: ShaderBackgroundProps = {
  variant: "static-mesh-gradient",
  colors: [INK, SAFFRON, PERIWINKLE, "#ffffff"],
  positions: 0,
  waveX: 0.6,
  waveXShift: 0.7,
  waveY: 0.7,
  waveYShift: 0.7,
  mixing: 0.5,
  grainMixer: 0,
  grainOverlay: 0,
  speed: 0,
}

export function AuthBackdrop({ className }: { className?: string }) {
  // Picked from the route rather than passed down, so the (auth) layout — which
  // wraps login, register and the SSO callback — stays a server component.
  const pathname = usePathname()
  const preset = pathname?.startsWith("/register") ? STATIC_MESH_DUSK : MESH

  return (
    <div
      aria-hidden
      className={`relative select-none overflow-hidden border-r border-border bg-surface ${className ?? ""}`}
    >
      <ShaderBackground {...preset} className="absolute inset-0" />
    </div>
  )
}
