"use client"

import { create } from "zustand"

export type ChatWindowSummary = {
  id: string
  title: string
  updatedAt: number
}

type PendingAction =
  | { type: "new"; nonce: number }
  | { type: "open"; id: string; nonce: number }

type ChatSessionState = {
  sessionId: string
  windows: ChatWindowSummary[]
  /** Used to hide an empty untitled draft from the Previous list. */
  activeTurnCount: number
  ready: boolean
  pending: PendingAction | null
  sync: (partial: {
    sessionId?: string
    windows?: ChatWindowSummary[]
    activeTurnCount?: number
    ready?: boolean
  }) => void
  requestNewChat: () => void
  requestOpen: (id: string) => void
  clearPending: () => void
}

let actionNonce = 0

export const useChatSessionStore = create<ChatSessionState>((set) => ({
  sessionId: "",
  windows: [],
  activeTurnCount: 0,
  ready: false,
  pending: null,
  sync: (partial) => set(partial),
  requestNewChat: () =>
    set({ pending: { type: "new", nonce: ++actionNonce } }),
  requestOpen: (id) =>
    set({ pending: { type: "open", id, nonce: ++actionNonce } }),
  clearPending: () => set({ pending: null }),
}))
