"use client"

import { ConnectorLogo } from "@/components/connector-logo"
import { AnimatedBadge } from "@/components/motion/animated-badge"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/motion/tabs"
import { Panel, SectionHead, SectionShell } from "@/components/landing/section"
import { CONNECTORS } from "@/lib/connectors"

/**
 * A tabbed panel rather than a four-card grid — one source at a time, with
 * room to actually say what it reads and how it gets there. Uses beui's Tabs
 * for the spring-settled pill indicator.
 */

const detail: Record<
  string,
  { reads: string[]; note: string }
> = {
  google: {
    reads: ["Drive documents", "Gmail threads", "Shared drives"],
    note: "OAuth consent from your Google Workspace account. Polling picks up new and changed files continuously.",
  },
  outlook: {
    reads: ["Outlook mail", "OneDrive files", "SharePoint documents"],
    note: "OAuth consent against Microsoft 365, on the same continuous polling schedule as Google.",
  },
  whatsapp: {
    reads: [
      "Customer conversations",
      "Shared documents and images",
      "Order and payment threads",
    ],
    note: "Messages arrive by inbound webhook from WhatsApp Business and are indexed on a daily pass.",
  },
  tally: {
    reads: ["Ledgers", "Vouchers", "GST data"],
    note: "A signed agent runs on the Windows machine Tally already lives on and pushes data out. Your ledgers are never handed to a cloud connector.",
  },
}

export function SourcesSection() {
  return (
    <SectionShell id="sources">
      <SectionHead
        eyebrow="Connected sources"
        heading="Every source your business actually runs on"
        lead="Each one lands on its own clock, in the background. Nothing to trigger, nothing to re-upload."
      />

      <div className="mt-12">
        <Tabs defaultValue="google" variant="pill">
          <TabsList className="mx-auto w-fit">
            {CONNECTORS.map((c) => (
              <TabsTrigger
                key={c.source}
                value={c.source}
                // Near-black pill read as heavy on a white, soft page. Blue →
                // violet keeps it in the brand's hues while staying dark
                // enough for the white label the component sets on the
                // active trigger.
                indicatorClassName="bg-[linear-gradient(120deg,oklch(0.48_0.2_268),oklch(0.55_0.17_288))] shadow-[0_3px_12px_-4px_oklch(0.48_0.2_268/0.55)]"
              >
                <span className="flex items-center gap-2">
                  <ConnectorLogo source={c.source} bare className="size-4" />
                  {c.shortLabel}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>

          {CONNECTORS.map((c) => (
            <TabsContent key={c.source} value={c.source} className="mt-8">
              <Panel className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:p-12">
                <div className="flex flex-col gap-5">
                  <div className="flex items-center gap-3.5">
                    <ConnectorLogo source={c.source} className="size-12" />
                    <div>
                      <h3 className="font-heading text-2xl font-normal">
                        {c.name}
                      </h3>
                      {/* beui AnimatedBadge — the dot pulses on the live
                          source, so "connected" is a state you can see. */}
                      <AnimatedBadge
                        className="mt-1.5"
                        size="sm"
                        status={c.available ? "success" : "neutral"}
                        pulse={c.available}
                        contentKey={c.source}
                      >
                        {c.available ? "Live today" : "Built, in rollout"}
                      </AnimatedBadge>
                    </div>
                  </div>

                  <p className="max-w-[46ch] text-[1rem] leading-relaxed text-muted-foreground">
                    {detail[c.source].note}
                  </p>

                  <dl className="mt-2 flex gap-10">
                    <div>
                      <dt className="font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground">
                        Connects
                      </dt>
                      <dd className="mt-1.5 text-[0.9375rem]">{c.handshake}</dd>
                    </div>
                    <div>
                      <dt className="font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground">
                        Syncs
                      </dt>
                      <dd className="mt-1.5 text-[0.9375rem]">{c.cadence}</dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-2xl bg-surface p-6">
                  <p className="font-mono text-[0.625rem] uppercase tracking-[0.12em] text-muted-foreground">
                    What SynQ reads
                  </p>
                  <ul className="mt-4 flex flex-col gap-3">
                    {detail[c.source].reads.map((item) => (
                      <li
                        key={item}
                        className="flex items-center gap-3 rounded-xl bg-card px-4 py-3 text-[0.9375rem]"
                      >
                        <ConnectorLogo
                          source={c.source}
                          bare
                          className="size-4"
                        />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </Panel>
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </SectionShell>
  )
}
