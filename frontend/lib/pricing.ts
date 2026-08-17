/**
 * ⚠️  PROVISIONAL PRICING — REPLACE BEFORE LAUNCH  ⚠️
 *
 * Every number in this file is a placeholder chosen to make the page render.
 * None of it has been set by the business. This is the only file that needs
 * editing when real pricing exists — the page, the toggle and the comparison
 * table all read from here.
 *
 * Checklist before this page can go public:
 *   [ ] monthly and annual figures for each tier
 *   [ ] seat and source limits confirmed
 *   [ ] decide whether Tally's on-prem agent is gated to Enterprise
 *   [ ] confirm GST handling and whether prices are inclusive
 */

export const PRICING_IS_PROVISIONAL = true

export type Tier = {
  id: string
  name: string
  tagline: string
  /** ₹ per month, billed monthly. null = "talk to us". */
  monthly: number | null
  /** ₹ per month, billed annually. null = "talk to us". */
  annual: number | null
  cta: string
  href: string
  featured?: boolean
  highlights: string[]
}

export const TIERS: Tier[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "One workspace, the sources most businesses start with.",
    monthly: 2999,
    annual: 2499,
    cta: "Request access",
    href: "/register",
    highlights: [
      "Up to 5 users",
      "Google Workspace and Outlook",
      "Unlimited questions",
      "Citations on every answer",
      "Email support",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "Every source, including the two nobody else reads.",
    monthly: 9999,
    annual: 8499,
    cta: "Request access",
    href: "/register",
    featured: true,
    highlights: [
      "Up to 25 users",
      "Everything in Starter",
      "WhatsApp Business",
      "Tally ledgers, vouchers and GST",
      "Priority support",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "For groups running several entities or many locations.",
    monthly: null,
    annual: null,
    cta: "Talk to us",
    href: "/register",
    highlights: [
      "Unlimited users",
      "Everything in Growth",
      "SSO and role policies",
      "Multiple Tally sites",
      "Custom retention and residency",
      "Named support contact",
    ],
  },
]

/** Row-by-row comparison. `true` renders a tick, a string renders as text. */
export const COMPARISON: {
  group: string
  rows: { label: string; values: (boolean | string)[] }[]
}[] = [
  {
    group: "Sources",
    rows: [
      { label: "Google Workspace", values: [true, true, true] },
      { label: "Outlook & OneDrive", values: [true, true, true] },
      { label: "WhatsApp Business", values: [false, true, true] },
      { label: "Tally ERP", values: [false, true, true] },
      { label: "Multiple Tally sites", values: [false, false, true] },
    ],
  },
  {
    group: "Answering",
    rows: [
      { label: "Questions per month", values: ["Unlimited", "Unlimited", "Unlimited"] },
      { label: "Citations on every claim", values: [true, true, true] },
    ],
  },
  {
    group: "Workspace",
    rows: [
      { label: "Users", values: ["5", "25", "Unlimited"] },
      { label: "Admin and member roles", values: [true, true, true] },
      { label: "SSO", values: [false, false, true] },
      { label: "Custom retention", values: [false, false, true] },
    ],
  },
]
