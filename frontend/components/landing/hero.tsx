import Link from "next/link"
import { Button } from "@/components/ui/button"
import { TextReveal } from "@/components/motion/text-reveal"
import { ConnectorLogo } from "@/components/connector-logo"
import { CONNECTORS } from "@/lib/connectors"

/**
 * Pure hero: status chip, headline, subhead, two pills, the sources it reads.
 *
 * The wash is no longer rendered here — it belongs to the marketing layout, so
 * it can start at y=0 instead of below the sticky nav's flow height. See the
 * comment in app/(marketing)/layout.tsx.
 *
 * 86vh, not 92: the header occupies ~60px of flow above this section, so the
 * fold still lands in roughly the same place.
 */
export function Hero() {
  return (
    <section className="relative flex min-h-[86vh] flex-col justify-center">
      <div className="mx-auto w-full max-w-6xl px-6 pt-10 pb-16">
        <div className="mx-auto flex max-w-4xl flex-col items-center text-center">
          {/* Pill inside the hairlines. Set small, lowercase and in muted grey
              rather than ink-blue — it's a grace note before the headline, not
              a claim competing with it. */}
          <div className="flex w-full max-w-xl items-center gap-4">
            <span aria-hidden className="h-px flex-1 bg-border" />
            <p className="shrink-0 rounded-full border border-border-subtle bg-card/70 px-3.5 py-1.5 text-[0.75rem] tracking-[0.01em] text-muted-foreground backdrop-blur-sm">
              one searchable index across four systems
            </p>
            <span aria-hidden className="h-px flex-1 bg-border" />
          </div>

          <TextReveal
            as="h1"
            text={["Every answer comes", "with its source."]}
            split="word"
            stagger={0.06}
            delay={0.1}
            className="font-heading mt-9 text-[clamp(3rem,8vw,6rem)] leading-[1.02] font-normal tracking-[-0.025em] text-balance"
          />

          <p className="mt-8 max-w-[54ch] text-[1.125rem] leading-relaxed text-foreground/70 text-pretty sm:text-xl">
            SynQ reads your Drive, inbox, WhatsApp Business chats and Tally
            ledgers as one. Ask in plain language — every line points back to
            the file, message or voucher behind it.
          </p>

          <div className="mt-11 flex flex-col items-center gap-3 sm:flex-row">
            <Button
              size="lg"
              className="h-13 rounded-full px-8 text-[1rem] transition-transform duration-200 ease-out hover:scale-[1.03] active:scale-[0.97]"
              nativeButton={false}
              render={<Link href="/login">Get started</Link>}
            />
            <Button
              size="lg"
              variant="outline"
              className="h-13 rounded-full border-border bg-card/70 px-8 text-[1rem] backdrop-blur-sm transition-transform duration-200 ease-out hover:scale-[1.03] active:scale-[0.97]"
              nativeButton={false}
              render={<Link href="#demo">See it work</Link>}
            />
          </div>
        </div>

        <div className="mt-24 flex flex-col items-center gap-6">
          <p className="font-mono text-[0.6875rem] uppercase tracking-[0.18em] text-muted-foreground">
            Reads across
          </p>
          <ul className="flex flex-wrap items-center justify-center gap-x-12 gap-y-5">
            {CONNECTORS.map((c) => (
              <li
                key={c.source}
                className="group flex items-center gap-2.5 text-[1rem] text-foreground/60 transition-colors duration-200 hover:text-foreground"
              >
                <ConnectorLogo
                  source={c.source}
                  bare
                  className="size-5 transition-transform duration-200 ease-out group-hover:scale-110"
                />
                {c.name}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
