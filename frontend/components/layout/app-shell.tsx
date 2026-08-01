"use client"

import { useRouter } from "next/navigation"
import Link from "next/link"
import { ChevronsUpDown, LogOut, PanelLeft, User } from "lucide-react"
import { Logo, LogoMark } from "@/components/brand/logo"
import { SidebarNav } from "@/components/layout/sidebar-nav"
import {
  AnimatedSidebar,
  AnimatedSidebarContent,
  AnimatedSidebarFooter,
  AnimatedSidebarHeader,
  AnimatedSidebarInset,
  AnimatedSidebarProvider,
  AnimatedSidebarRail,
  AnimatedSidebarTrigger,
  useAnimatedSidebar,
} from "@/components/motion/animated-sidebar"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { useAuthStore } from "@/lib/auth/auth-store"

/**
 * One sidebar, using beui's `AnimatedSidebar` as it ships.
 *
 * A previous version added a second, narrow icon rail beside it. That was a
 * misread of the reference and it's gone — one panel, `collapsible="icon"`, so
 * collapsing leaves the icon rail the component already provides rather than a
 * separate column. ⌘B, the mobile offcanvas and the shared-layout active
 * indicator all come from the component.
 */

/**
 * Collapsed means collapsed *on desktop* — the mobile panel is an offcanvas
 * sheet that is always full width when it's open at all.
 */
function useCollapsed() {
  const { open, isMobile } = useAnimatedSidebar()
  return !isMobile && !open
}

function SidebarBrand() {
  const collapsed = useCollapsed()

  // Collapsed, the trigger takes the whole row — it is the only way back, so it
  // can't be the thing that gets hidden. The mark returns with the panel.
  if (collapsed) {
    return (
      <AnimatedSidebarTrigger className="mx-auto size-9 text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground">
        <PanelLeft className="size-4" />
      </AnimatedSidebarTrigger>
    )
  }

  return (
    <div className="flex items-center justify-between gap-2">
      <Link
        href="/chat"
        className="flex h-9 items-center rounded-lg px-1 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Logo size="sm" />
      </Link>
      <AnimatedSidebarTrigger className="size-8 shrink-0 text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground">
        <PanelLeft className="size-4" />
      </AnimatedSidebarTrigger>
    </div>
  )
}

function SidebarAccount() {
  const router = useRouter()
  const collapsed = useCollapsed()
  const email = useAuthStore((s) => s.email)
  const clearSession = useAuthStore((s) => s.clearSession)

  // No invented display name. /me and the JWT expose neither a name nor an
  // email, so the label is the address captured at login, or a generic role.
  const label = email ?? "SynQ AI user"

  function handleLogout() {
    clearSession()
    router.push("/login")
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            aria-label="Account"
            className="flex w-full items-center gap-2.5 rounded-xl px-1.5 py-1.5 text-left outline-none transition-colors duration-150 hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Avatar className="size-7 shrink-0">
              <AvatarFallback>
                <User className="size-3.5" />
              </AvatarFallback>
            </Avatar>
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 truncate text-[0.8125rem]">
                  {label}
                </span>
                <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
              </>
            )}
          </button>
        }
      />
      <DropdownMenuContent align="start" side="top" className="w-56">
        <div className="truncate px-2 py-1.5 text-xs text-muted-foreground">
          {label}
        </div>
        <DropdownMenuItem
          render={<Link href="/settings/account">Account settings</Link>}
        />
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={handleLogout}>
          <LogOut className="size-4" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AnimatedSidebarProvider>
      <AnimatedSidebar
        collapsible="icon"
        ariaLabel="Workspace"
        panelClassName="border-sidebar-border bg-sidebar"
      >
        <AnimatedSidebarHeader>
          <SidebarBrand />
        </AnimatedSidebarHeader>

        <AnimatedSidebarContent>
          <SidebarNav />
        </AnimatedSidebarContent>

        <AnimatedSidebarFooter className="border-sidebar-border">
          <SidebarAccount />
        </AnimatedSidebarFooter>

        <AnimatedSidebarRail />
      </AnimatedSidebar>

      {/* `h-svh`, not the inset's default `min-h-svh`. A min-height gives its
          children no definite height to resolve against, so a page saying
          `h-full` fell back to `auto` — which is why a long chat transcript
          grew the column and pushed the composer off the bottom instead of
          scrolling under a pinned one. */}
      <AnimatedSidebarInset className="h-svh">
        {/* Mobile only. On desktop the panel header owns the toggle — having one
            here as well meant two controls for closing the same sidebar. */}
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border-subtle px-3 md:hidden">
          <AnimatedSidebarTrigger className="text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground">
            <PanelLeft className="size-4" />
          </AnimatedSidebarTrigger>
          <Link
            href="/chat"
            aria-label="SynQ AI"
            className="rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <LogoMark size="sm" />
          </Link>
        </header>

        {/* Pages own their own scrolling. Chat needs a pinned composer under a
            scrolling transcript, which an overflow-y-auto wrapper out here
            would have made impossible. */}
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </AnimatedSidebarInset>
    </AnimatedSidebarProvider>
  )
}
