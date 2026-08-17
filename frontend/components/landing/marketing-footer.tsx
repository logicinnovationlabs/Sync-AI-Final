import Link from "next/link"
import { LogoMark } from "@/components/brand/logo"
import { ConnectorLogo } from "@/components/connector-logo"
import { FooterWordmark } from "@/components/landing/footer-wordmark"
import { CONNECTORS } from "@/lib/connectors"

/**
 * Structured footer: identity block on the left, link columns across, and the
 * wordmark set very large along the bottom edge — a full stop rather than a
 * thin strip of legalese.
 */

const columns = [
  {
    heading: "Product",
    links: [
      { href: "/#demo", label: "See it work" },
      { href: "/#sources", label: "Sources" },
      { href: "/#how-it-works", label: "How it works" },
      { href: "/pricing", label: "Pricing" },
      { href: "/#faq", label: "FAQ" },
    ],
  },
  {
    heading: "Sources",
    links: CONNECTORS.map((c) => ({ href: "/#sources", label: c.name })),
  },
  {
    heading: "Account",
    links: [
      { href: "/login", label: "Sign in" },
      { href: "/register", label: "Create an account" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { href: "/privacy", label: "Privacy" },
      { href: "/terms", label: "Terms" },
      { href: "/#security", label: "Security" },
    ],
  },
]

export function MarketingFooter() {
  return (
    // Light grey ground, as the reference does — it separates the footer from
    // the white page without needing a rule across the viewport.
    <footer className="relative overflow-hidden bg-surface">
      <div className="mx-auto max-w-6xl px-6 pt-16">
        <div className="grid gap-12 lg:grid-cols-12">
          <div className="flex flex-col gap-5 lg:col-span-3">
            <div className="flex items-center gap-2.5">
              <LogoMark size="lg" />
              <span className="font-heading text-[1.75rem] leading-none font-medium tracking-[-0.015em]">
                SynQ AI
              </span>
            </div>
            <p className="max-w-[34ch] text-[0.9375rem] leading-relaxed text-muted-foreground">
              One searchable knowledge base across the systems an Indian
              business already runs on.
            </p>

            <div className="mt-2 flex flex-col gap-2.5">
              <p className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
                Connects to
              </p>
              <div className="flex items-center gap-3">
                {CONNECTORS.map((c) => (
                  <span
                    key={c.source}
                    title={c.name}
                    className="flex size-9 items-center justify-center rounded-xl border border-border-subtle bg-card transition-colors duration-200 hover:border-border"
                  >
                    <ConnectorLogo source={c.source} bare className="size-4" />
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="grid gap-10 sm:grid-cols-2 lg:col-span-8 lg:col-start-5 lg:grid-cols-4">
            {columns.map((col) => (
              <nav key={col.heading} className="flex flex-col gap-3.5">
                <p className="font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground">
                  {col.heading}
                </p>
                {col.links.map((link) => (
                  <Link
                    key={link.label}
                    href={link.href}
                    className="w-fit text-[0.9375rem] text-muted-foreground transition-colors duration-200 hover:text-foreground"
                  >
                    {link.label}
                  </Link>
                ))}
              </nav>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-border-subtle py-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[0.8125rem] text-muted-foreground">
            © {new Date().getFullYear()} SynQ AI. All rights reserved.
          </p>
          <p className="font-mono text-[0.6875rem] text-muted-foreground">
            Built for Indian SMBs
          </p>
        </div>
      </div>

      {/* <FooterWordmark /> */}
    </footer>
  )
}
