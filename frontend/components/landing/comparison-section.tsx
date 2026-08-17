"use client"

import { motion } from "motion/react"
import { Check, Minus } from "lucide-react"
import { Panel, SectionHead, SectionShell } from "@/components/landing/section"
import { EASE_OUT, SPRING_PRESS } from "@/lib/ease"

const rows = [
  { capability: "Gmail and Google Drive", generic: true },
  { capability: "Outlook and OneDrive", generic: false },
  { capability: "WhatsApp Business conversations", generic: false },
  { capability: "Tally ledgers, vouchers, GST data", generic: false },
  { capability: "Ledgers stay on-prem", generic: false },
  { capability: "Citation back to the source record", generic: true },
]

function Cell({ on, delay }: { on: boolean; delay: number }) {
  return on ? (
    <motion.span
      initial={{ scale: 0, opacity: 0 }}
      whileInView={{ scale: 1, opacity: 1 }}
      viewport={{ once: true }}
      transition={{ ...SPRING_PRESS, delay }}
      className="flex justify-center"
    >
      <Check className="size-[1.125rem] text-success" strokeWidth={2.2} />
    </motion.span>
  ) : (
    <Minus className="mx-auto size-[1.125rem] text-muted-foreground/35" />
  )
}

export function ComparisonSection() {
  return (
    <SectionShell>
      <SectionHead
        eyebrow="Why generic RAG falls short"
        heading="Built for how Indian SMBs actually work"
        lead="Tools that index email and drive stop at the boundary of the two systems an Indian business actually settles accounts in."
      />

      <Panel className="mx-auto mt-12 max-w-3xl p-0 sm:p-0">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-border-subtle">
              <th className="px-6 py-4 text-[0.8125rem] font-normal text-muted-foreground">
                Capability
              </th>
              <th className="w-32 px-3 py-4 text-center text-[0.8125rem] font-normal text-muted-foreground">
                Generic RAG
              </th>
              <th className="w-32 px-3 py-4 text-center text-[0.8125rem] font-medium">
                SynQ AI
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <motion.tr
                key={row.capability}
                initial={{ opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.6 }}
                transition={{ duration: 0.4, ease: EASE_OUT, delay: i * 0.06 }}
                className="group border-b border-border-subtle last:border-0"
              >
                <td className="px-6 py-4 text-[0.9375rem] transition-colors duration-200 group-hover:bg-secondary/60">
                  {row.capability}
                </td>
                <td className="px-3 py-4 transition-colors duration-200 group-hover:bg-secondary/60">
                  <Cell on={row.generic} delay={i * 0.06 + 0.12} />
                </td>
                {/* The column that carries the argument stays tinted. */}
                <td className="bg-surface px-3 py-4 transition-colors duration-200 group-hover:bg-ink-blue/[0.06]">
                  <Cell on delay={i * 0.06 + 0.18} />
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </SectionShell>
  )
}
