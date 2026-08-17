import { ImageResponse } from "next/og"

export const size = { width: 32, height: 32 }
export const contentType = "image/png"

/**
 * The concentric-aperture mark from components/brand/logo.tsx, generated rather
 * than shipped as a binary — one source of truth for the geometry, and nothing
 * to keep in sync by hand.
 *
 * Drawn with nested divs because ImageResponse's Satori renderer supports a
 * flexbox subset of CSS, not SVG primitives. Inked near-black so it stays
 * readable on both light and dark browser chrome.
 */
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#ffffff",
        }}
      >
        <div
          style={{
            width: 26,
            height: 26,
            borderRadius: "50%",
            border: "2.4px solid #14161f",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              width: 15,
              height: 15,
              borderRadius: "50%",
              border: "2.4px solid #14161f",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 4.5,
                height: 4.5,
                borderRadius: "50%",
                background: "#14161f",
              }}
            />
          </div>
        </div>
      </div>
    ),
    size
  )
}
