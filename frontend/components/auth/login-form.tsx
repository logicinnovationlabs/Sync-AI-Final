"use client"

import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Input } from "@/components/motion/input"
import { StatefulButton } from "@/components/motion/button/stateful"
import { login } from "@/lib/api/auth"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
import { tenantFromHost } from "@/lib/auth/tenant"

const loginSchema = z.object({
  email: z.email({ error: "Enter a valid email address." }).trim(),
  password: z.string().min(1, { error: "Enter your password." }),
})

type LoginValues = z.infer<typeof loginSchema>

/**
 * Reserves the error row. beui's `Input` mounts its message into an
 * `AnimatePresence` below the field, so a form that is 88px tall when valid
 * becomes 108px when it isn't — which shifted the page and could push it past
 * the viewport into a scrollbar. Holding the space means the height is constant
 * and the message simply fades into a gap that was always there.
 *
 * label 20 + gap 6 + field 44 + gap 6 + message 16 ≈ 5.75rem.
 */
const FIELD = { root: "min-h-[5.75rem]" }

export function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setSession = useAuthStore((s) => s.setSession)
  const [submitting, setSubmitting] = useState(false)
  // Sign-in failures belong next to the fields that caused them, not in a toast
  // in the corner. The `ApiError` message is shown verbatim so a wrong tenant
  // reads differently from a wrong password.
  const [formError, setFormError] = useState<string | null>(null)

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    // Stays empty on purpose — pre-filled demo credentials are flagged in
    // PRODUCT.md as a hardening issue.
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: LoginValues) {
    setSubmitting(true)
    setFormError(null)
    try {
      const res = await login({
        ...values,
        // Not asked for — derived from the hostname. See lib/auth/tenant.ts.
        tenant_subdomain: tenantFromHost(),
      })
      setSession({
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        email: values.email,
      })
      const next = searchParams.get("next") ?? "/chat"
      router.push(next)
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Something went wrong. Try again."
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col">
      <Controller
        control={control}
        name="email"
        render={({ field }) => (
          <Input
            {...field}
            id="email"
            type="email"
            label="Email"
            placeholder="you@company.com"
            autoComplete="email"
            classNames={FIELD}
            error={errors.email?.message}
          />
        )}
      />

      <Controller
        control={control}
        name="password"
        render={({ field }) => (
          <Input
            {...field}
            id="password"
            type="password"
            label="Password"
            autoComplete="current-password"
            classNames={FIELD}
            error={errors.password?.message}
          />
        )}
      />

      {/* Also a reserved slot — a form-level error appearing must not move the
          submit button out from under the cursor. */}
      <div className="min-h-[2.75rem] pt-1">
        {formError && (
          <p
            role="alert"
            className="rounded-xl border border-destructive/25 bg-destructive/5 px-3 py-2 text-[0.8125rem] text-destructive"
          >
            {formError}
          </p>
        )}
      </div>

      <StatefulButton
        type="submit"
        size="lg"
        variant="primary"
        state={submitting ? "loading" : "idle"}
        loadingText="Signing in…"
        className="w-full"
      >
        Sign in
      </StatefulButton>
    </form>
  )
}
