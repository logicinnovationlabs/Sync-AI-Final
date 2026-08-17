"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Input } from "@/components/motion/input"
import { StatefulButton } from "@/components/motion/button/stateful"
import { login, register as createUser } from "@/lib/api/auth"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"

const registerSchema = z.object({
  tenant_subdomain: z
    .string()
    .min(1, { error: "Enter your workspace." })
    .trim(),
  display_name: z.string().min(1, { error: "Enter your name." }).trim(),
  email: z.email({ error: "Enter a valid email address." }).trim(),
  // The backend publishes no password policy, so this is a floor, not a claim
  // about what it enforces. Don't invent rules it doesn't have.
  password: z.string().min(8, { error: "Use at least 8 characters." }),
})

type RegisterValues = z.infer<typeof registerSchema>

/** Reserved error row — see the note in `login-form.tsx`. */
const FIELD = { root: "min-h-[5.75rem]" }

export function RegisterForm() {
  const router = useRouter()
  const setSession = useAuthStore((s) => s.setSession)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const {
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      tenant_subdomain: "",
      display_name: "",
      email: "",
      password: "",
    },
  })

  async function onSubmit(values: RegisterValues) {
    setSubmitting(true)
    setFormError(null)
    try {
      await createUser({
        tenant_subdomain: values.tenant_subdomain,
        display_name: values.display_name,
        email: values.email,
        password: values.password,
      })

      // Creating the account doesn't return a session, so sign in with the
      // credentials we just set. If that second call fails the account still
      // exists — send them to sign in rather than looping here.
      try {
        const res = await login({
          tenant_subdomain: values.tenant_subdomain,
          email: values.email,
          password: values.password,
        })
        setSession({
          accessToken: res.access_token,
          refreshToken: res.refresh_token,
          email: values.email,
        })
        router.push("/chat")
      } catch {
        router.push("/login")
      }
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
      {/* Paired so five fields still fit a viewport without scrolling. */}
      <div className="grid gap-x-3 sm:grid-cols-2">
        <Controller
          control={control}
          name="tenant_subdomain"
          render={({ field }) => (
            <Input
              {...field}
              id="tenant_subdomain"
              label="Workspace"
              placeholder="acme"
              autoComplete="organization"
              classNames={FIELD}
              error={errors.tenant_subdomain?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="display_name"
          render={({ field }) => (
            <Input
              {...field}
              id="display_name"
              label="Your name"
              placeholder="Priya Nair"
              autoComplete="name"
              classNames={FIELD}
              error={errors.display_name?.message}
            />
          )}
        />
      </div>

      <Controller
        control={control}
        name="email"
        render={({ field }) => (
          <Input
            {...field}
            id="email"
            type="email"
            label="Work email"
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
            autoComplete="new-password"
            classNames={FIELD}
            error={errors.password?.message}
          />
        )}
      />

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
        loadingText="Creating account…"
        className="w-full"
      >
        Create account
      </StatefulButton>
    </form>
  )
}
