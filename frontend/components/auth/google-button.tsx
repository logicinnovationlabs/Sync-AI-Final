"use client"

import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import { ConnectorLogo } from "@/components/connector-logo"
import { EASE_OUT } from "@/lib/ease"

/**
 * Continue with Google.
 *
 * Rendered at full strength on both `/login` and `/register` — this is the shape
 * the surface has once the backend lands, and a permanently dimmed control is a
 * worse thing to look at than a live one.
 *
 * It does not navigate yet, and can't be faked into working:
 *
 *   · `GET /auth/sso/login` raises 500 unless OIDC is configured, and
 *     `sso_callback` ends at a stub that never issues a session
 *     (`backend/app/api/v1/auth.py:159`).
 *   · `GET /connectors/google/authorize` *does* work, but it is the connector
 *     consent flow — it grants Drive and Gmail read scopes to an already
 *     signed-in tenant. It cannot stand in for sign-in.
 *
 * So pressing it says so rather than throwing you at a 500. To wire it up: drop
 * `useState`, render as an `<a href={…/auth/sso/login}>`, delete the notice.
 *
 * The mark is the real Google one, reused from `components/connector-logo.tsx`
 * rather than redrawn.
 */
export function GoogleButton({ label = "Continue with Google" }: { label?: string }) {
  const [notice, setNotice] = useState(false)

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setNotice(true)}
        className="flex h-12 w-full cursor-pointer items-center justify-center gap-3 rounded-full border border-border bg-card text-[0.9375rem] font-medium transition-[background-color,border-color,transform] duration-150 ease-out outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:scale-[0.985]"
      >
        <ConnectorLogo source="google" bare className="size-[1.125rem]" />
        {label}
      </button>

      <AnimatePresence initial={false}>
        {notice && (
          <motion.p
            role="status"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: EASE_OUT }}
            className="overflow-hidden text-center text-xs text-muted-foreground"
          >
            Google sign-in isn&apos;t issuing sessions yet — use your email and
            password below.
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
