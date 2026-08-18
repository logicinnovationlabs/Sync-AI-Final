"use client"

import { useSyncExternalStore } from "react"
import { create } from "zustand"
import { persist } from "zustand/middleware"
import { decodeAccessToken, isExpired, type AccessTokenClaims } from "@/lib/auth/jwt"
import {
  isDevAdminOverrideEnabled,
  DEV_ADMIN_SCOPES,
} from "@/lib/auth/dev-overrides"
import { isAdmin as scopesIsAdmin } from "@/lib/auth/scopes"

const SESSION_COOKIE = "synq_session"

function setSessionCookie(maxAgeSeconds: number) {
  if (typeof document === "undefined") return
  document.cookie = `${SESSION_COOKIE}=1; path=/; samesite=lax; max-age=${Math.max(0, maxAgeSeconds)}`
}

function clearSessionCookie() {
  if (typeof document === "undefined") return
  document.cookie = `${SESSION_COOKIE}=; path=/; max-age=0`
}

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  claims: AccessTokenClaims | null
  /** Captured at login time only — /me returns no email/display_name today. */
  email: string | null
  setSession: (params: {
    accessToken: string
    refreshToken: string
    email: string
  }) => void
  clearSession: () => void
  isAuthenticated: () => boolean
  /** Scopes including the local dev-only admin override, if enabled. */
  effectiveScopes: () => string[]
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      claims: null,
      email: null,

      setSession: ({ accessToken, refreshToken, email }) => {
        const claims = decodeAccessToken(accessToken)
        set({ accessToken, refreshToken, claims, email })
        if (claims) {
          setSessionCookie(claims.exp - Math.floor(Date.now() / 1000))
        }
      },

      clearSession: () => {
        set({ accessToken: null, refreshToken: null, claims: null, email: null })
        clearSessionCookie()
      },

      isAuthenticated: () => {
        const { claims } = get()
        return !!claims && !isExpired(claims)
      },

      effectiveScopes: () => {
        const { claims } = get()
        const base = claims?.scopes ?? []
        if (isDevAdminOverrideEnabled()) {
          return Array.from(new Set([...base, ...DEV_ADMIN_SCOPES]))
        }
        return base
      },

      isAdmin: () => scopesIsAdmin(get().effectiveScopes()),
    }),
    {
      name: "synq-auth",
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        claims: state.claims,
        email: state.email,
      }),
    }
  )
)

/**
 * Persist rehydration can finish in a microtask before React hydrates, so the
 * first client render would see a logged-in admin while SSR saw an empty
 * store. `getServerSnapshot` stays false so both trees match; the real
 * session appears on the subsequent client render.
 */
export function useAuthHydrated() {
  return useSyncExternalStore(
    (onChange) => useAuthStore.persist.onFinishHydration(onChange),
    () => useAuthStore.persist.hasHydrated(),
    () => false
  )
}
