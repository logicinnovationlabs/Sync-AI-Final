"use client"

import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { PermissionDenied } from "@/components/shared/permission-denied"

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const hydrated = useAuthHydrated()
  const isAdmin = useAuthStore((s) => s.isAdmin())

  if (!hydrated) {
    return null
  }

    if (!isAdmin) {
    return <PermissionDenied requiredScope="admin.users.read" />
  }

  return <>{children}</>
}
