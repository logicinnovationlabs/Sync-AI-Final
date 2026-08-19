import { ImageResponse } from "next/og"

export const alt = "SynQ AI — Every answer comes with its source"
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

/**
 * The share card: the haze across the crown, the headline set below it.
 *
 * Satori (ImageResponse's renderer) has no filter: blur() and no oklch(), so
 * the wash is approximated with layered radial-gradients in sRGB rather than
 * the real --haze-* tokens. Close enough at 1200×630, and it keeps the card
 * self-contained — no fonts to fetch, no images to embed.
 */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#ffffff",
          padding: 72,
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: -260,
            left: -100,
            right: -100,
            height: 700,
            background:
              "radial-gradient(ellipse 55% 60% at 30% 40%, rgba(247,164,96,0.85), rgba(255,255,255,0) 70%), radial-gradient(ellipse 60% 55% at 65% 55%, rgba(163,164,232,0.8), rgba(255,255,255,0) 72%), radial-gradient(ellipse 45% 50% at 50% 70%, rgba(160,142,222,0.55), rgba(255,255,255,0) 75%)",
          }}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              border: "3px solid #14161f",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                border: "3px solid #14161f",
              }}
            />
          </div>
          <div style={{ fontSize: 34, color: "#14161f", letterSpacing: -0.5 }}>
            SynQ AI
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          <div
            style={{
              fontSize: 84,
              lineHeight: 1.05,
              letterSpacing: -2.5,
              color: "#14161f",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <span>Every answer comes</span>
            <span>with its source.</span>
          </div>
          <div style={{ fontSize: 30, color: "#5c5f6b", letterSpacing: -0.3 }}>
            Drive · Outlook · WhatsApp Business · Tally, read as one.
          </div>
        </div>
      </div>
    ),
    size
  )
}
