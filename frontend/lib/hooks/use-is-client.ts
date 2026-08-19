"use client"

import { useSyncExternalStore } from "react"

function subscribe() {
  return () => {}
}

/** False during SSR and the hydration pass; true on the next client render. */
export function useIsClient() {
  return useSyncExternalStore(subscribe, () => true, () => false)
}
