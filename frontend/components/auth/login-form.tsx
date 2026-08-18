"use client"

import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Input } from "@/components/motion/input"
import { StatefulButton } from "@/components/motion/button/stateful"
import { LocalAdminCredentials } from "@/components/auth/local-admin-credentials"
import { getMe, login } from "@/lib/api/auth"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
import { isAdmin as scopesIsAdmin } from "@/lib/auth/scopes"
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
    setValue,
    formState: { errors },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    // Fields stay empty; development shows fillable local admin and member
    // hints so seeded Alpha accounts can be used without guessing passwords.
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: LoginValues) {
    setSubmitting(true)
    setFormError(null)
    try {
      const tenant = tenantFromHost()
      if (!tenant) {
        setFormError(
          "No workspace on this host. Set NEXT_PUBLIC_DEFAULT_TENANT (seed tenant is `alpha`) or sign in from a tenant subdomain."
        )
        return
      }
      const res = await login({
        ...values,
        tenant_subdomain: tenant,
      })
      // Prove the stored token is the one Block A issued: /me must accept it.
      const me = await getMe(res.access_token)
      setSession({
        accessToken: res.access_token,
        refreshToken: res.refresh_token,
        email: values.email,
      })
      const admin =
        res.role === "admin" ||
        me.role === "admin" ||
        scopesIsAdmin(me.scopes ?? [])
      const next =
        searchParams.get("next") ??
        (me.must_change_password || res.must_change_password
          ? "/settings/account"
          : admin
            ? "/admin"
            : "/chat")
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

      <div className="mt-6">
        <LocalAdminCredentials
          includeMember
          onUse={({ email, password }) => {
            setValue("email", email, { shouldValidate: true })
            setValue("password", password, { shouldValidate: true })
          }}
        />
      </div>
    </form>
  )
}
