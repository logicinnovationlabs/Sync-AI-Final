import { Suspense } from "react"
import Link from "next/link"
import type { Metadata } from "next"
import { LoginForm } from "@/components/auth/login-form"
import { GoogleButton } from "@/components/auth/google-button"

export const metadata: Metadata = {
  title: "Sign in",
}

export default function LoginPage() {
  return (
    <div className="flex flex-col">
      <h1 className="text-center font-heading text-[clamp(1.875rem,3.4vw,2.375rem)] leading-[1.1] font-normal tracking-[-0.02em]">
        Sign in
      </h1>
      <p className="mt-2 text-center text-sm text-muted-foreground">
        Every answer comes back with the record it came from.
      </p>

      <div className="mt-8">
        <GoogleButton />
      </div>

      <div className="my-6 flex items-center gap-4">
        <hr className="flex-1 border-border-subtle" />
        <span className="text-xs text-muted-foreground">or</span>
        <hr className="flex-1 border-border-subtle" />
      </div>

      <Suspense>
        <LoginForm />
      </Suspense>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link
          href="/register"
          className="text-ink-blue underline-offset-4 hover:underline"
        >
          Create one
        </Link>
      </p>
    </div>
  )
}
