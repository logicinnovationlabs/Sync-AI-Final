"use client"

import { useRouter, usePathname } from "next/navigation"
import { FileText, MessageSquare, Plus, Plug, ShieldCheck } from "lucide-react"
import {
  AnimatedSidebarGroup,
  AnimatedSidebarGroupContent,
  AnimatedSidebarGroupLabel,
  AnimatedSidebarMenu,
  AnimatedSidebarMenuItem,
  AnimatedSidebarMenuButton,
  useAnimatedSidebar,
} from "@/components/motion/animated-sidebar"
import { useAuthHydrated, useAuthStore } from "@/lib/auth/auth-store"
import { useChatSessionStore } from "@/lib/chat/session-store"
import { useHydrateChatSessionStore } from "@/lib/chat/use-hydrate-chat-session-store"
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

function NavItem({
  href,
  label,
  icon: Icon,
}: {
  href: string
  label: string
  icon: typeof FileText
}) {
  const pathname = usePathname()
  const router = useRouter()
  const active = pathname === href || pathname.startsWith(`${href}/`)

  return (
    <AnimatedSidebarMenuItem
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
        router.push(href)
      }}
    >
      <AnimatedSidebarMenuButton
        href={href}
        isActive={active}
        icon={<Icon className="size-4" />}
        className={cn(
          "min-h-10 transition-colors duration-150",
          active ? ACTIVE_PILL : HOVER
        )}
      >
        {label}
      </AnimatedSidebarMenuButton>
    </AnimatedSidebarMenuItem>
  )
}

function SidebarChatHistory() {
  const router = useRouter()
  const pathname = usePathname()
  const { open, isMobile } = useAnimatedSidebar()
  const collapsed = !isMobile && !open
  const sessionId = useChatSessionStore((s) => s.sessionId)
  const windows = useChatSessionStore((s) => s.windows)
  const activeTurnCount = useChatSessionStore((s) => s.activeTurnCount)
  const requestNewChat = useChatSessionStore((s) => s.requestNewChat)
  const requestOpen = useChatSessionStore((s) => s.requestOpen)

  const history = windows.filter(
    (w) => w.id !== sessionId || w.title !== "New chat" || activeTurnCount > 0
  )

  function goNew() {
    requestNewChat()
    if (pathname !== "/chat") router.push("/chat")
  }

  function goOpen(id: string) {
    requestOpen(id)
    if (pathname !== "/chat") router.push("/chat")
  }

  if (collapsed) {
    return (
      <div className="px-1 pt-1">
        <button
          type="button"
          onClick={goNew}
          aria-label="New chat"
          title="New chat"
          className="mx-auto grid size-9 place-items-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Plus className="size-4" />
        </button>
      </div>
    )
  }

  return (
    <AnimatedSidebarGroup className="min-h-0 flex-1 px-0 pt-2">
      <div className="px-1 pb-2">
        <button
          type="button"
          onClick={goNew}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-border-subtle bg-card px-3 py-2 text-sm font-medium transition-colors hover:bg-muted"
        >
          <Plus className="size-4" />
          New chat
        </button>
      </div>
      <AnimatedSidebarGroupLabel className="px-3">
        Previous
      </AnimatedSidebarGroupLabel>
      <AnimatedSidebarGroupContent className="min-h-0 flex-1">
        <ul className="max-h-[min(52vh,24rem)] space-y-0.5 overflow-y-auto overscroll-contain px-1 pb-2">
          {history.length === 0 ? (
            <li className="px-2 py-2 text-sm text-muted-foreground">
              No earlier chats yet.
            </li>
          ) : (
            history.map((w) => {
              const active = pathname.startsWith("/chat") && w.id === sessionId
              return (
                <li key={w.id}>
                  <button
                    type="button"
                    onClick={() => goOpen(w.id)}
                    className={cn(
                      "w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors",
                      active
                        ? "bg-ink-blue/8 font-medium text-ink-blue"
                        : "text-foreground hover:bg-muted"
                    )}
                  >
                    {w.title || "New chat"}
                  </button>
                </li>
              )
            })
          )}
        </ul>
      </AnimatedSidebarGroupContent>
    </AnimatedSidebarGroup>
  )
}

export function SidebarNav() {
  useHydrateChatSessionStore()
  const hydrated = useAuthHydrated()
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const items = hydrated && isAdmin ? [...baseItems, ...adminItems] : baseItems

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1 pt-1">
      <nav aria-label="Main">
        <AnimatedSidebarMenu className="gap-1.5">
          {items.map((item) => (
            <NavItem key={item.href} {...item} />
          ))}
        </AnimatedSidebarMenu>
      </nav>

      {/* Same theme. Claude-style layout: New chat + previous chats live in this
          sidebar under Connectors/Chat — second history column removed. */}
      <SidebarChatHistory />
    </div>
  )
}
