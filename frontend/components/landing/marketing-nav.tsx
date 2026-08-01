"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { motion, useMotionValueEvent, useScroll } from "motion/react"
import { useEffect, useState } from "react"
import { Menu, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Logo } from "@/components/brand/logo"
import { Drawer } from "@/components/motion/drawer"
import { Magnetic } from "@/components/motion/magnetic"
import { SPRING_LAYOUT } from "@/lib/ease"
import { cn } from "@/lib/utils"

/**
 * Anchors are root-relative (`/#demo`, not `#demo`).
 *
 * A bare `#demo` resolves against whatever page you're on, so from /pricing —
 * where no such section exists — every one of these links did nothing at all.
 * With the leading slash the browser navigates home first, then scrolls.
 */
const links = [
  { href: "/#demo", id: "demo", label: "See it work" },
  { href: "/#sources", id: "sources", label: "Sources" },
  { href: "/#how-it-works", id: "how-it-works", label: "How it works" },
  { href: "/#security", id: "security", label: "Security" },
]

/** Real routes. Active by pathname rather than by scroll position. */
const routeLinks = [{ href: "/pricing", label: "Pricing" }]

export function MarketingNav() {
  const { scrollY } = useScroll()
  const pathname = usePathname()
  const onHome = pathname === "/"

  const [lifted, setLifted] = useState(false)
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useMotionValueEvent(scrollY, "change", (y) => {
    const next = y > 24
    setLifted((prev) => (prev === next ? prev : next))
  })

  // Scrollspy, home page only — there are no tracked sections anywhere else.
  useEffect(() => {
    // No clearing needed off-home: isActive() branches on `onHome`, so a stale
    // section id is simply never read.
    if (!onHome) return
    const sections = links
      .map((l) => document.getElementById(l.id))
      .filter((el): el is HTMLElement => el !== null)
    if (sections.length === 0) return

    const visible = new Set<string>()
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id)
          else visible.delete(entry.target.id)
        }
        const next = links.find((l) => visible.has(l.id))
        // Hold the last match rather than dropping to null. Half this page is
        // sections the nav doesn't list (the star, the roles, the FAQ), so
        // clearing on every gap made the indicator flicker off for most of a
        // scroll — which is why it read as "not working".
        if (next) setActiveSection(next.id)
      },
      { rootMargin: "-45% 0px -50% 0px" }
    )

    sections.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [onHome])

  const isActive = (key: string) =>
    onHome ? activeSection === key : pathname === key

  return (
    // top-4, not top-0 with padding — the capsule keeps a visible gap from
    // the viewport edge at every scroll position instead of docking flush.
    <header className="sticky top-4 z-30 px-4">
      {/*
        The width used to animate from 1024 → 880 on a motion spring. That was
        the lag: a spring writes a new max-width every frame, each frame forces
        a layout, and re-laying out an element with `backdrop-blur-xl` makes the
        compositor re-sample the blur across its whole area — on top of Lenis
        already driving the scroll. Width is now fixed and only colour and
        shadow move, on a plain CSS transition. Nothing here touches layout.
      */}
      <nav
        data-lifted={lifted || undefined}
        className={cn(
          "mx-auto flex max-w-5xl items-center gap-8 rounded-full border border-white/60 py-3 pr-3 pl-6 backdrop-blur-xl",
          "bg-[color-mix(in_oklch,var(--card),transparent_22%)] shadow-[0_8px_30px_-12px_oklch(0.3_0.05_275/0.18)]",
          "transition-[background-color,box-shadow] duration-300 ease-out",
          "data-lifted:bg-[color-mix(in_oklch,var(--card),transparent_8%)] data-lifted:shadow-[0_12px_40px_-14px_oklch(0.3_0.05_275/0.3)]"
        )}
      >
        <Link href="/" className="transition-opacity hover:opacity-70">
          <Logo size="sm" />
        </Link>

        <div className="hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              aria-current={isActive(link.id) ? "true" : undefined}
              className={cn(
                "relative rounded-full px-3 py-1.5 text-[0.875rem] transition-colors duration-200",
                isActive(link.id)
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {isActive(link.id) && (
                <motion.span
                  layoutId="nav-active"
                  transition={SPRING_LAYOUT}
                  className="absolute inset-0 -z-10 rounded-full bg-secondary"
                />
              )}
              {link.label}
            </a>
          ))}
          {routeLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={isActive(link.href) ? "page" : undefined}
              className={cn(
                "relative rounded-full px-3 py-1.5 text-[0.875rem] transition-colors duration-200",
                isActive(link.href)
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {isActive(link.href) && (
                <motion.span
                  layoutId="nav-active"
                  transition={SPRING_LAYOUT}
                  className="absolute inset-0 -z-10 rounded-full bg-secondary"
                />
              )}
              {link.label}
            </Link>
          ))}
        </div>

        {/* No size="sm". The reference's nav pills are ~56px tall and read as
            real controls; small ones make the whole bar look like a prototype. */}
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            className="hidden h-11 rounded-full px-5 text-[0.9375rem] sm:inline-flex"
            nativeButton={false}
            render={<Link href="/login">Sign in</Link>}
          />
          {/* beui Magnetic — the button leans toward the cursor. It no-ops on
              touch and under reduced motion, so no scale/transform fallback
              is needed alongside it. */}
          <Magnetic strength={0.2}>
            <Button
              className="h-11 rounded-full px-6 text-[0.9375rem]"
              nativeButton={false}
              render={<Link href="/login">Get started</Link>}
            />
          </Magnetic>
          {/* Below md the links above are hidden and there was nothing in
              their place — the marketing site had no navigation at all on a
              phone. */}
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            aria-expanded={menuOpen}
            className="flex size-11 cursor-pointer items-center justify-center rounded-full text-foreground transition-colors duration-200 hover:bg-secondary md:hidden"
          >
            <Menu className="size-5" />
          </button>
        </div>
      </nav>

      <Drawer
        open={menuOpen}
        onOpenChange={setMenuOpen}
        side="right"
        ariaLabel="Site menu"
      >
        <div className="flex items-center justify-between px-5 py-4">
          <Logo size="sm" />
          <button
            type="button"
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
            className="flex size-9 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground"
          >
            <X className="size-[1.125rem]" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 px-3 pt-4">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="rounded-2xl px-4 py-3 text-[1.0625rem] text-foreground transition-colors duration-200 hover:bg-secondary"
            >
              {link.label}
            </a>
          ))}
          {routeLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="rounded-2xl px-4 py-3 text-[1.0625rem] text-foreground transition-colors duration-200 hover:bg-secondary"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="flex flex-col gap-2.5 border-t border-border-subtle p-5">
          <Button
            variant="outline"
            className="h-11 w-full rounded-full"
            nativeButton={false}
            render={
              <Link href="/login" onClick={() => setMenuOpen(false)}>
                Sign in
              </Link>
            }
          />
          <Button
            className="h-11 w-full rounded-full"
            nativeButton={false}
            render={
              <Link href="/register" onClick={() => setMenuOpen(false)}>
                Create an account
              </Link>
            }
          />
        </div>
      </Drawer>
    </header>
  )
}
