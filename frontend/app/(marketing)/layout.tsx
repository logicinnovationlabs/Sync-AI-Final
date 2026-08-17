import { Haze } from "@/components/brand/haze"
import { MarketingNav } from "@/components/landing/marketing-nav"
import { MarketingFooter } from "@/components/landing/marketing-footer"
import { SmoothScroll } from "@/components/motion/smooth-scroll"

/**
 * Lenis is back. It wasn't the cause of the dead scroll — `h-full` on <html>
 * plus `min-h-full` on <body> in the root layout was pinning the document to
 * viewport height, so Lenis had nothing to scroll. Root layout now uses
 * `min-h-screen` on <body> only.
 *
 * The haze lives *here*, not in the hero. <MarketingNav> is `sticky`, and a
 * sticky element still occupies its flow height (~60px) — so anything inside
 * <main> starts 60px down and the wash could never reach y=0 no matter how it
 * was anchored. That dead 60px was the white band across the top. Hoisting the
 * wash to the layout makes it the page's ground rather than the hero's
 * decoration, and the nav capsule gets to float over live colour, which is what
 * marketing-nav.tsx wanted all along.
 */
export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <SmoothScroll className="relative isolate flex flex-1 flex-col">
      <Haze height={1120} />
      <MarketingNav />
      <main className="flex-1">{children}</main>
      <MarketingFooter />
    </SmoothScroll>
  )
}
