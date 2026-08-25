"use client"

import { useEffect } from "react"
import {
  listAssistantSessions,
} from "@/lib/api/assistant"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import {
  useChatSessionStore,
  type ChatWindowSummary,
} from "@/lib/chat/session-store"

function storageKey(tenantId: string, userId: string) {
  return `synq.chat.v1.${tenantId}.${userId}`
}

function loadLocalWindows(
  tenantId: string,
  userId: string
): { activeId: string; windows: ChatWindowSummary[]; turnCount: number } {
  const empty = { activeId: "", windows: [] as ChatWindowSummary[], turnCount: 0 }
  if (typeof window === "undefined") return empty
  try {
    const raw = localStorage.getItem(storageKey(tenantId, userId))
    if (!raw) return empty
    const parsed = JSON.parse(raw) as {
      activeId?: string
      windows?: ChatWindowSummary[]
      turnsById?: Record<string, unknown[]>
    }
    const activeId = parsed.activeId || ""
    const turns = activeId && parsed.turnsById ? parsed.turnsById[activeId] : []
    return {
      activeId,
      windows: Array.isArray(parsed.windows) ? parsed.windows : [],
      turnCount: Array.isArray(turns) ? turns.length : 0,
    }
  } catch {
    return empty
  }
}

/**
 * Keeps the main-sidebar chat list warm even when ChatView is not mounted
 * (e.g. user is on Documents / Connectors).
 */
export function useHydrateChatSessionStore() {
  const hydrated = useAuthHydrated()
  const token = useAuthStore((s) => s.accessToken)
  const claims = useAuthStore((s) => s.claims)
  const authenticated = useAuthStore((s) => s.isAuthenticated())
  const sync = useChatSessionStore((s) => s.sync)
  const tenantId = claims?.tenant_id || "alpha"
  const userId = claims?.sub || "anon"

  useEffect(() => {
    if (!hydrated || !authenticated) {
      sync({ ready: false, windows: [], sessionId: "", activeTurnCount: 0 })
      return
    }

    const local = loadLocalWindows(tenantId, userId)
    sync({
      sessionId: local.activeId,
      windows: local.windows,
      activeTurnCount: local.turnCount,
      ready: true,
    })

    if (!token) return
    let cancelled = false
    void (async () => {
      try {
        const remote = await listAssistantSessions(token)
        if (cancelled) return
        sync({
          windows: (() => {
            const byId = new Map<string, ChatWindowSummary>()
            for (const row of remote) {
              byId.set(row.session_id, {
                id: row.session_id,
                title: row.title || "New chat",
                updatedAt: row.updated_at
                  ? Date.parse(row.updated_at)
                  : Date.now(),
              })
            }
            for (const w of local.windows) {
              if (!byId.has(w.id)) byId.set(w.id, w)
            }
            return [...byId.values()].sort((a, b) => b.updatedAt - a.updatedAt)
          })(),
        })
      } catch {
        // local list is enough
      }
    })()

    return () => {
      cancelled = true
    }
  }, [authenticated, hydrated, sync, tenantId, token, userId])
}
