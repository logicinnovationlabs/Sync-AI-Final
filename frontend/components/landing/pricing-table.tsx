"use client"

import Link from "next/link"
import { Fragment, useState } from "react"
import { motion } from "motion/react"
import { Check, Minus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/motion/switch"
import { EASE_OUT, SPRING_PRESS } from "@/lib/ease"
import { COMPARISON, PRICING_IS_PROVISIONAL, TIERS } from "@/lib/pricing"
import { cn } from "@/lib/utils"

/** ₹ with Indian digit grouping — 2,499 not 2.499. */
const inr = (n: number) => `₹${n.toLocaleString("en-IN")}`

export function PricingTable() {
  const [annual, setAnnual] = useState(true)

  return (
    <>
      {PRICING_IS_PROVISIONAL && (
        <div className="mx-auto mb-10 max-w-2xl rounded-2xl border border-dashed border-warning/50 bg-warning/5 px-5 py-4 text-center">
          <p className="text-[0.875rem] leading-relaxed text-foreground/80">
            <span className="font-medium">These figures are placeholders.</span>{" "}
            Pricing hasn&apos;t been set — replace{" "}
            <code className="font-mono text-[0.8125rem]">lib/pricing.ts</code>{" "}
            and clear the flag before this page goes public.
          </p>
        </div>
      )}

      {/* Billing toggle — beui switch. */}
      <div className="flex items-center justify-center gap-3">
        <span
          className={cn(
            "text-[0.9375rem] transition-colors duration-200",
            annual ? "text-muted-foreground" : "text-foreground"
          )}
        >
          Monthly
        </span>
        <Switch checked={annual} onCheckedChange={setAnnual} />
        <span
          className={cn(
            "text-[0.9375rem] transition-colors duration-200",
            annual ? "text-foreground" : "text-muted-foreground"
          )}
        >
          Annual
        </span>
        <span className="rounded-full bg-success/12 px-2.5 py-1 text-[0.75rem] font-medium text-success">
          Save ~15%
        </span>
      </div>

      <div className="mt-12 grid gap-5 lg:grid-cols-3">
        {TIERS.map((tier, i) => {
          const price = annual ? tier.annual : tier.monthly
          return (
            <motion.div
              key={tier.id}
              initial={{ opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.5, ease: EASE_OUT, delay: i * 0.06 }}
              className={cn(
                "flex flex-col gap-6 rounded-[1.75rem] border p-8",
                tier.featured
                  ? "border-ink-blue/35 bg-card shadow-[0_10px_50px_-16px_oklch(0.48_0.2_268/0.28)]"
                  : "border-border-subtle bg-card"
              )}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2.5">
                  <h3 className="font-heading text-2xl font-normal">
                    {tier.name}
                  </h3>
                  {tier.featured && (
                    <span className="rounded-full bg-ink-blue/12 px-2.5 py-0.5 text-[0.6875rem] font-medium text-ink-blue">
                      Most businesses
                    </span>
                  )}
                </div>
                <p className="text-[0.9375rem] leading-relaxed text-muted-foreground">
                  {tier.tagline}
                </p>
              </div>

              <div className="flex items-baseline gap-1.5">
                {price === null ? (
                  <span className="font-heading text-[2.5rem] leading-none font-normal">
                    Custom
                  </span>
                ) : (
                  <>
                    {/* Keyed on the billing period so the figure swaps rather
                        than silently mutating — the toggle needs to be felt. */}
                    <motion.span
                      key={`${tier.id}-${annual}`}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={SPRING_PRESS}
                      className="font-heading text-[2.5rem] leading-none font-normal tabular-nums"
                    >
                      {inr(price)}
                    </motion.span>
                    <span className="text-[0.9375rem] text-muted-foreground">
                      /month
                    </span>
                  </>
                )}
              </div>

              <Button
                size="lg"
                variant={tier.featured ? "default" : "outline"}
                className="h-12 w-full rounded-full text-[0.9375rem]"
                nativeButton={false}
                render={<Link href={tier.href}>{tier.cta}</Link>}
              />

              <ul className="flex flex-col gap-3">
                {tier.highlights.map((h) => (
                  <li key={h} className="flex items-start gap-2.5 text-[0.9375rem]">
                    <Check className="mt-0.5 size-4 shrink-0 text-success" />
                    {h}
                  </li>
                ))}
              </ul>
            </motion.div>
          )
        })}
      </div>

      {/* Full comparison */}
      <div className="mt-20 overflow-x-auto">
        <table className="w-full min-w-[42rem] border-collapse text-left">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-4 text-[0.8125rem] font-normal text-muted-foreground">
                Compare
              </th>
              {TIERS.map((t) => (
                <th
                  key={t.id}
                  className="w-40 px-4 py-4 text-center text-[0.9375rem] font-medium"
                >
                  {t.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {COMPARISON.map((group) => (
              <Fragment key={group.group}>
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 pt-8 pb-2 font-mono text-[0.625rem] uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    {group.group}
                  </td>
                </tr>
                {group.rows.map((row) => (
                  <tr
                    key={row.label}
                    className="group border-b border-border-subtle"
                  >
                    <td className="px-4 py-3.5 text-[0.9375rem] transition-colors duration-200 group-hover:bg-secondary/60">
                      {row.label}
                    </td>
                    {row.values.map((v, i) => (
                      <td
                        key={i}
                        className="px-4 py-3.5 text-center text-[0.875rem] transition-colors duration-200 group-hover:bg-secondary/60"
                      >
                        {v === true ? (
                          <Check className="mx-auto size-[1.125rem] text-success" />
                        ) : v === false ? (
                          <Minus className="mx-auto size-[1.125rem] text-muted-foreground/35" />
                        ) : (
                          v
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
