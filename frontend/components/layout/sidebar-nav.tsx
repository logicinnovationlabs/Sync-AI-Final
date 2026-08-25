"use client"

import { useRouter, usePathname } from "next/navigation"
import { MessageSquare, FileText, Plug, ShieldCheck } from "lucide-react"
import {
  AnimatedSidebarMenu,
  AnimatedSidebarMenuItem,
  AnimatedSidebarMenuButton,
} from "@/components/motion/animated-sidebar"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { cn } from "@/lib/utils"

const baseItems = [
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/connectors", label: "Connectors", icon: Plug },
  { href: "/chat", label: "Chat", icon: MessageSquare },
]

const adminItems = [
  { href: "/admin", label: "Admin", icon: ShieldCheck },
]

/**
 * ── Making the states visible on a white panel ───────────────────────────────
 * beui's `AnimatedSidebarMenuButton` ships with `hover:text-foreground` and no
 * hover background at all, and its active indicator is `bg-muted`
 * (`oklch(0.965)`). On a white sidebar that is a 3.5% difference — invisible.
 *
 * Greying the whole panel was tried and rejected. Instead the two states are
 * told apart by *kind*, not by shade:
 *
 *   · active — a tinted `--ink-blue` wash with a matching hairline, and the
 *     label in ink blue. It reads as selected, not merely as hovered, because
 *     it is the only coloured thing in the column.
 *   · hover — a plain neutral fill. Quiet, and unmistakably not the active one.
 *
 * The indicator is an internal `motion.span` with no prop to style it, so it's
 * reached with a child selector — safe because the selector is only applied
 * when `active`, and the indicator is the first child exactly then.
 */
const ACTIVE_PILL =
  "text-ink-blue [&>span:first-child]:bg-ink-blue/8 [&>span:first-child]:ring-1 [&>span:first-child]:ring-ink-blue/15"

// Tailwind v4 already scopes `hover:` behind `(hover: hover)`, so a touch tap
// won't latch this on.
const HOVER = "hover:bg-muted hover:text-foreground"

export function SidebarNav() {
  const pathname = usePathname()
  const router = useRouter()
  const hydrated = useAuthHydrated()
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const items = hydrated && isAdmin ? [...baseItems, ...adminItems] : baseItems

  return (
    <nav aria-label="Main" className="pt-1">
      {/* beui's menu sets `gap-0.5` — 2px between rows, which packs three
          destinations into a block that reads as one object. */}
      <AnimatedSidebarMenu className="gap-1.5">
        {items.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`)

          return (
            <AnimatedSidebarMenuItem
              key={item.href}
              // `AnimatedSidebarMenuButton` renders a bare <a> when given an
              // href, not a next/link — so an uncaught click is a full document
              // reload, which throws away the client cache and re-hydrates the
              // session on every nav. Intercepting here keeps the real href
              // (right-click, status bar, keyboard) while routing on the client.
              // Modified clicks fall through so cmd/middle-click still opens a
              // new tab.
              onClickCapture={(event) => {
                if (
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey ||
                  event.altKey ||
                  event.button !== 0
                ) {
                  return
                }
                event.preventDefault()
                router.push(item.href)
              }}
            >
              <AnimatedSidebarMenuButton
                href={item.href}
                isActive={active}
                icon={<item.icon className="size-4" />}
                className={cn(
                  "min-h-10 transition-colors duration-150",
                  active ? ACTIVE_PILL : HOVER
                )}
              >
                {item.label}
              </AnimatedSidebarMenuButton>
            </AnimatedSidebarMenuItem>
          )
        })}
      </AnimatedSidebarMenu>
    </nav>
  )
}
