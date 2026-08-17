"use client"

import { useAuthStore } from "@/lib/auth/auth-store"
import { PermissionDenied } from "@/components/shared/permission-denied"

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const isAdmin = useAuthStore((s) => s.isAdmin())

  if (!isAdmin) {
    return <PermissionDenied requiredScope="connectors.write" />
  }

  return <>{children}</>
}
