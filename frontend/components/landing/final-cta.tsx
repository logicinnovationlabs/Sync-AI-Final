import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Haze } from "@/components/brand/haze"

/**
 * The haze returns to close the page — the same wash that opened it, so the
 * page begins and ends in colour and stays white in between.
 */
export function FinalCta() {
  return (
    <section className="relative isolate overflow-hidden">
      <div className="absolute inset-x-0 bottom-0 -z-10 h-[620px] rotate-180">
        <Haze height={620} intensity={0.85} />
      </div>

      <div className="mx-auto max-w-6xl px-6 py-24 lg:py-32">
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-7 text-center">
          <h2 className="font-heading text-[clamp(2.25rem,4.6vw,3.5rem)] leading-[1.08] font-normal tracking-[-0.02em] text-balance">
            Stop searching four systems for one answer.
          </h2>
          <p className="max-w-[46ch] text-[1.0625rem] leading-relaxed text-muted-foreground text-pretty">
            Connect your workspace and ask your first question. Every answer
            comes back with the record it came from.
          </p>

          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <Button
              size="lg"
              className="h-12 rounded-full px-7 text-[0.9375rem]"
              nativeButton={false}
              render={<Link href="/login">Get started</Link>}
            />
            <Button
              size="lg"
              variant="outline"
              className="h-12 rounded-full border-border bg-card/70 px-7 text-[0.9375rem] backdrop-blur-sm"
              nativeButton={false}
              render={<Link href="/login">Book a demo</Link>}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
