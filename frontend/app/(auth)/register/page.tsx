import Link from "next/link"
import type { Metadata } from "next"
import { RegisterForm } from "@/components/auth/register-form"
import { GoogleButton } from "@/components/auth/google-button"

export const metadata: Metadata = {
  title: "Create an account",
}

export default function RegisterPage() {
  return (
    <div className="flex flex-col">
      <h1 className="text-center font-heading text-[clamp(1.875rem,3.4vw,2.375rem)] leading-[1.1] font-normal tracking-[-0.02em]">
        Create an account
      </h1>
      <p className="mt-2 text-center text-sm text-muted-foreground">
        Join an existing workspace — an admin has to invite you first.
      </p>

      <div className="mt-8">
        <GoogleButton label="Sign up with Google" />
      </div>

      <div className="my-6 flex items-center gap-4">
        <hr className="flex-1 border-border-subtle" />
        <span className="text-xs text-muted-foreground">or</span>
        <hr className="flex-1 border-border-subtle" />
      </div>

      <RegisterForm />

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link
          href="/login"
          className="text-ink-blue underline-offset-4 hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  )
}
