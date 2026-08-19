"use client"

import Link from "next/link"

/**
 * Self-serve register is blocked — not disabled silently.
 *
 * Block N's live contract is authenticated admin invite:
 * POST /admin/users with Bearer admin JWT, body
 * `{ email, display_name, role? }`, server-generated password.
 * The suhani form posted `{ tenant_subdomain, email, password, display_name }`
 * with no auth. That is a contract mismatch; we do not shim it and we do not
 * change Block N from the frontend side.
 */
export function RegisterForm() {
  return (
    <div className="flex flex-col gap-4">
      <div
        role="status"
        className="rounded-2xl border border-border bg-muted/40 px-4 py-3 text-[0.875rem] leading-relaxed text-muted-foreground"
      >
        Accounts are created by a workspace admin, not from this page. Sign in
        with an invited email, or ask an admin to invite you. Self-serve signup
        is not part of the current backend contract.
      </div>
      <Link
        href="/login"
        className="flex h-12 w-full items-center justify-center rounded-full bg-primary text-sm font-medium text-primary-foreground"
      >
        Back to sign in
      </Link>
    </div>
  )
}
