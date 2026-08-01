import Link from "next/link"
import { AuthBackdrop } from "@/components/auth/auth-backdrop"
import { Logo } from "@/components/brand/logo"

/**
 * Split shell — shader on the left, everything else on the right.
 *
 * Wraps `/login`, `/register` and `/sso/callback`, so the right column holds
 * arbitrary children at a comfortable measure rather than assuming a form.
 *
 * ── No page scroll, and nothing moves on validation ──────────────────────────
 * Two earlier attempts got this wrong. Centring the column meant growth
 * re-solved the centring and moved everything; top-anchoring stopped the *top*
 * moving but the block still grew, outran the viewport and gained a scrollbar.
 *
 * The real fix is in the forms: every field reserves its error row, so the
 * column's height is constant whether or not it's valid. Once that's true, this
 * can be `h-svh overflow-hidden` and simply fit.
 *
 * `overflow-y-auto` stays on the column purely as a safety valve for very short
 * windows — with a constant height it doesn't engage at any normal size, and
 * without it the submit button would be unreachable at ~500px tall.
 *
 * Below `lg` the shader panel is removed outright rather than shrunk.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="grid h-svh overflow-hidden bg-background lg:grid-cols-2">
      <AuthBackdrop className="hidden lg:block" />

      <div className="flex flex-col overflow-y-auto px-6 py-10 sm:px-10 lg:px-14">
        <div className="m-auto w-full max-w-md py-4">
          <Link
            href="/"
            className="mx-auto mb-9 flex w-fit rounded-lg outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
          >
            <Logo size="md" />
          </Link>

          {children}
        </div>
      </div>
    </div>
  )
}
