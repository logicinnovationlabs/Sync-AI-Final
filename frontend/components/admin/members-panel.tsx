"use client"

import { Fragment, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  deactivateAdminUser,
  listAdminUsers,
  listMemberDocuments,
  listMembers,
  patchAdminUser,
  removeAccessOverride,
  setAccessOverride,
  transferOwnership,
  type DocumentListItem,
} from "@/lib/api/admin"
import { ApiError } from "@/lib/api/client"
import { useAuthStore } from "@/lib/auth/auth-store"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

const ROLE_STYLES: Record<string, string> = {
  owner: "bg-violet-100 text-violet-800",
  admin: "bg-sky-100 text-sky-800",
  member: "bg-emerald-100 text-emerald-800",
  viewer: "bg-stone-100 text-stone-700",
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-[0.6875rem] font-medium capitalize",
        ROLE_STYLES[role] ?? "bg-muted text-muted-foreground",
      )}
    >
      {role}
    </span>
  )
}

function AccessControl({
  doc,
  userId,
  pending,
  onChange,
}: {
  doc: DocumentListItem
  userId: string
  pending: boolean
  onChange: (next: "default" | "allow" | "deny") => void
}) {
  const current = doc.access_override ?? "default"
  const options: Array<{ value: "default" | "allow" | "deny"; label: string }> = [
    { value: "default", label: "Default" },
    { value: "allow", label: "Allow" },
    { value: "deny", label: "Deny" },
  ]
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "text-[0.6875rem] font-medium",
          current === "deny" && "text-red-600",
          current === "allow" && "text-emerald-700",
          current === "default" && "text-muted-foreground",
        )}
      >
        {current === "deny" ? "Denied by admin" : current === "allow" ? "Allowed by admin" : "Default ACL"}
      </span>
      <div className="flex rounded-lg border border-border p-0.5">
        {options.map((option) => (
          <Button
            key={option.value}
            type="button"
            size="xs"
            variant={current === option.value ? "secondary" : "ghost"}
            disabled={pending}
            aria-pressed={current === option.value}
            aria-label={`${option.label} access for ${doc.title}`}
            onClick={() => {
              if (option.value !== current) onChange(option.value)
            }}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  )
}

export function MembersPanel() {
  const token = useAuthStore((s) => s.accessToken)
  const isOwner = useAuthStore((s) => s.isOwner())
  const queryClient = useQueryClient()
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null)
  const [ownershipTransferTarget, setOwnershipTransferTarget] = useState<string | null>(null)

  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => listAdminUsers(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const members = useQuery({
    queryKey: ["admin-members"],
    queryFn: () => listMembers(token!),
    enabled: Boolean(token),
    retry: false,
  })

  const memberDocuments = useQuery({
    queryKey: ["admin-member-documents", selectedMemberId],
    queryFn: () => listMemberDocuments(token!, selectedMemberId!),
    enabled: Boolean(token) && Boolean(selectedMemberId),
    retry: false,
  })

  const roleChangeMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      patchAdminUser(token!, userId, { role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] })
      queryClient.invalidateQueries({ queryKey: ["admin-members"] })
    },
  })

  const deactivateMutation = useMutation({
    mutationFn: (userId: string) => deactivateAdminUser(token!, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] })
      queryClient.invalidateQueries({ queryKey: ["admin-members"] })
    },
  })

  const ownershipTransferMutation = useMutation({
    mutationFn: (targetUserId: string) => transferOwnership(token!, targetUserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] })
      queryClient.invalidateQueries({ queryKey: ["admin-members"] })
      setOwnershipTransferTarget(null)
    },
  })

  const setOverrideMutation = useMutation({
    mutationFn: ({
      userId,
      documentId,
      access,
    }: {
      userId: string
      documentId: string
      access: "allow" | "deny"
    }) => setAccessOverride(token!, userId, documentId, access),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-member-documents", selectedMemberId] })
    },
  })

  const removeOverrideMutation = useMutation({
    mutationFn: ({ userId, documentId }: { userId: string; documentId: string }) =>
      removeAccessOverride(token!, userId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-member-documents", selectedMemberId] })
    },
  })

  const countsByUser = new Map(
    (members.data ?? []).map((member) => [
      member.principal_id,
      {
        owned: member.owned_count ?? member.document_count,
        shared: member.shared_count ?? 0,
      },
    ]),
  )
  const overridePending = setOverrideMutation.isPending || removeOverrideMutation.isPending

  return (
    <section>
      <h2 className="text-sm font-medium">Members</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Everyone in this workspace. Open a row to allow or deny that person access to a document they own or that is shared with them.
      </p>

      {(users.isFetching || members.isFetching) && (
        <p className="mt-3 text-sm text-muted-foreground">Loading members…</p>
      )}
      {users.error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {users.error instanceof ApiError ? users.error.message : "Failed to load members"}
        </p>
      )}
      {members.error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {members.error instanceof ApiError ? members.error.message : "Failed to load document counts"}
        </p>
      )}

      {users.data && (
        <div className="mt-3 overflow-hidden rounded-2xl border border-border-subtle">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="px-4">Member</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Documents</TableHead>
                <TableHead className="w-[1%] text-right px-4"> </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.data.map((user) => {
                const expanded = selectedMemberId === user.principal_id
                const counts = countsByUser.get(user.principal_id)
                const isCurrentUserOwner = user.role === "owner"
                const canEditRole = isOwner && !isCurrentUserOwner
                const canDeactivate = isOwner && !isCurrentUserOwner && user.is_active
                const canReactivate = isOwner && !isCurrentUserOwner && !user.is_active
                const availableRoles = isOwner
                  ? ["owner", "admin", "member", "viewer"]
                  : ["member", "viewer"]
                const docs = memberDocuments.data ?? []
                const ownedDocs = docs.filter((doc) => doc.assignment === "owned")
                const sharedDocs = docs.filter((doc) => doc.assignment === "shared")

                return (
                  <Fragment key={user.principal_id}>
                    <TableRow key={user.principal_id} aria-expanded={expanded}>
                      <TableCell className="px-4">
                        <div className="flex min-w-0 flex-col">
                          <span className="font-medium text-foreground">{user.display_name}</span>
                          <span className="text-xs text-muted-foreground">{user.email}</span>
                          {!user.is_active && (
                            <span className="text-xs text-red-600">Inactive</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <RoleBadge role={user.role} />
                          {canEditRole && (
                            <select
                              aria-label={`Role for ${user.display_name}`}
                              value={user.role}
                              onChange={(event) =>
                                roleChangeMutation.mutate({
                                  userId: user.principal_id,
                                  role: event.target.value,
                                })
                              }
                              disabled={roleChangeMutation.isPending}
                              className="rounded-md border border-border bg-background px-2 py-1 text-xs"
                            >
                              {availableRoles.map((role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground whitespace-normal">
                        {counts ? (
                          <>
                            <span className="text-foreground">{counts.owned}</span> owned
                            <span className="mx-1.5 text-border-subtle">·</span>
                            <span className="text-foreground">{counts.shared}</span> shared
                          </>
                        ) : (
                          "…"
                        )}
                      </TableCell>
                      <TableCell className="px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setSelectedMemberId((current) =>
                                current === user.principal_id ? null : user.principal_id,
                              )
                            }
                          >
                            {expanded ? "Hide documents" : "See documents"}
                          </Button>
                          {canDeactivate && (
                            <button
                              type="button"
                              onClick={() => deactivateMutation.mutate(user.principal_id)}
                              disabled={deactivateMutation.isPending}
                              className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
                            >
                              Deactivate
                            </button>
                          )}
                          {canReactivate && (
                            <button
                              type="button"
                              onClick={() => deactivateMutation.mutate(user.principal_id)}
                              disabled={deactivateMutation.isPending}
                              className="text-xs text-emerald-700 hover:text-emerald-900 disabled:opacity-50"
                            >
                              Reactivate
                            </button>
                          )}
                          {isOwner && !isCurrentUserOwner && user.is_active && (
                            <button
                              type="button"
                              onClick={() => setOwnershipTransferTarget(user.principal_id)}
                              className="text-xs text-violet-700 hover:text-violet-900"
                            >
                              Transfer ownership
                            </button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                    {expanded && (
                      <TableRow key={`${user.principal_id}-docs`} className="hover:bg-transparent">
                        <TableCell colSpan={4} className="bg-muted/30 px-4 py-4">
                          <p className="mb-3 text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">Owned</span> means they created or hold the file.
                            {" "}
                            <span className="font-medium text-foreground">Shared</span> means ACL grants them access.
                            Deny hides the document from their search regardless of ACL.
                          </p>
                          {memberDocuments.isFetching && (
                            <p className="text-xs text-muted-foreground">Loading documents…</p>
                          )}
                          {memberDocuments.error && (
                            <p role="alert" className="text-xs text-destructive">
                              {memberDocuments.error instanceof ApiError
                                ? memberDocuments.error.message
                                : "Failed to load documents"}
                            </p>
                          )}
                          {memberDocuments.data && memberDocuments.data.length === 0 && (
                            <p className="text-xs text-muted-foreground">
                              No owned or shared documents for this member.
                            </p>
                          )}
                          {memberDocuments.data && memberDocuments.data.length > 0 && (
                            <div className="max-h-80 overflow-y-auto rounded-xl border border-border-subtle bg-background">
                              <ul className="divide-y divide-border-subtle">
                                {[...ownedDocs, ...sharedDocs].map((doc) => (
                                  <li key={doc.document_id} className="flex flex-col gap-2 px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                                    <div className="min-w-0">
                                      <p className="truncate text-sm font-medium">{doc.title}</p>
                                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                        <span
                                          className={cn(
                                            "inline-flex rounded-full px-2 py-0.5 text-[0.6875rem] font-medium",
                                            doc.assignment === "owned"
                                              ? "bg-sky-50 text-sky-800"
                                              : "bg-amber-50 text-amber-800",
                                          )}
                                        >
                                          {doc.assignment === "owned" ? "Owned" : "Shared"}
                                        </span>
                                        <span className="text-[0.6875rem] text-muted-foreground">{doc.source_type}</span>
                                      </div>
                                    </div>
                                    <AccessControl
                                      doc={doc}
                                      userId={user.principal_id}
                                      pending={overridePending}
                                      onChange={(next) => {
                                        if (next === "default") {
                                          removeOverrideMutation.mutate({
                                            userId: user.principal_id,
                                            documentId: doc.document_id,
                                          })
                                        } else {
                                          setOverrideMutation.mutate({
                                            userId: user.principal_id,
                                            documentId: doc.document_id,
                                            access: next,
                                          })
                                        }
                                      }}
                                    />
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {ownershipTransferTarget && users.data && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-lg bg-background p-6 shadow-lg">
            <h3 className="mb-2 text-lg font-medium">Transfer ownership</h3>
            <p className="mb-4 text-sm text-muted-foreground">
              Transfer ownership to{" "}
              <strong className="text-foreground">
                {users.data.find((item) => item.principal_id === ownershipTransferTarget)?.display_name}
              </strong>
              ? You will become an admin. Tokens for both accounts are revoked. This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOwnershipTransferTarget(null)}>
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => ownershipTransferMutation.mutate(ownershipTransferTarget)}
                disabled={ownershipTransferMutation.isPending}
              >
                {ownershipTransferMutation.isPending ? "Transferring…" : "Confirm transfer"}
              </Button>
            </div>
            {ownershipTransferMutation.error && (
              <p className="mt-2 text-xs text-red-600">
                {ownershipTransferMutation.error instanceof ApiError
                  ? ownershipTransferMutation.error.message
                  : "Failed to transfer ownership"}
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
