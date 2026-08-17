import type { ConnectorSourceType } from "@/lib/connectors"

/**
 * The scripted material behind the landing-page demo.
 *
 * Answers are split at citation boundaries so the marks can land on their own
 * beat as the text streams, rather than appearing pre-baked inside a sentence.
 *
 * Everything here is invented sample data for a fictional business — it stands
 * in for a real workspace, and is deliberately not framed as a customer,
 * a case study or a result. See SUMMARY.md §7.
 */

export type Token = {
  text: string
  /** Renders as citation mark [n] instead of text. */
  cite?: number
  strong?: boolean
}

export type DemoSource = {
  n: number
  source: ConnectorSourceType
  title: string
  snippet: string
  meta: string
}

export type DemoAnswer = {
  id: string
  /** The pill label — kept short enough to sit on one line at 390px. */
  label: string
  /** Who in the business asks this. Drives the roles section. */
  role: string
  /** What that person is actually doing when they ask it. */
  roleNote: string
  question: string
  answer: Token[]
  sources: DemoSource[]
}

/** The distinct connectors an answer draws on, in the order they're cited. */
export function sourcesUsed(d: DemoAnswer): ConnectorSourceType[] {
  return [...new Set(d.sources.map((s) => s.source))]
}

export const DEMO_ANSWERS: DemoAnswer[] = [
  {
    id: "receivables",
    label: "Chase an unpaid invoice",
    role: "The owner",
    roleNote:
      "Wants to know who owes money and whether the claim that it was paid holds up against the books.",
    question: "Has Meridian Traders cleared the March invoices?",
    answer: [
      { text: "Not yet — " },
      { text: "₹2,84,500 ", strong: true },
      {
        text: "is still outstanding across three invoices, all past their net-30 date",
      },
      { text: "", cite: 1 },
      { text: "", cite: 3 },
      { text: ". They messaged that payment was released on 12 March" },
      { text: "", cite: 2 },
      { text: ", but nothing has posted against the ledger since." },
    ],
    sources: [
      {
        n: 1,
        source: "tally",
        title: "Voucher #TV-2026-0481",
        snippet: "Meridian Traders · Sundry Debtors · ₹2,84,500 Dr",
        meta: "Tally · 22 min ago",
      },
      {
        n: 2,
        source: "whatsapp",
        title: "Meridian Traders",
        snippet: "“payment released on the 12th, please check”",
        meta: "WhatsApp · 12 Mar",
      },
      {
        n: 3,
        source: "google",
        title: "INV-2026-0334.pdf",
        snippet: "Net 30 · due 04 Mar · ₹1,12,000",
        meta: "Drive · 3 min ago",
      },
    ],
  },
  {
    id: "quote",
    label: "Recall an old quote",
    role: "The ops lead",
    roleNote:
      "Needs the number that was actually agreed, across a document, an email thread and a chat.",
    question: "What did we quote Kalyani Industries last quarter?",
    answer: [
      { text: "You quoted " },
      { text: "₹8,40,000 ", strong: true },
      { text: "for the 400-unit order on 14 January" },
      { text: "", cite: 1 },
      { text: ", then revised it to " },
      { text: "₹7,95,000 ", strong: true },
      { text: "over email after they pushed back on freight" },
      { text: "", cite: 2 },
      { text: ". They confirmed the revised figure on WhatsApp the same week" },
      { text: "", cite: 3 },
      { text: ", but no purchase order has come through yet." },
    ],
    sources: [
      {
        n: 1,
        source: "google",
        title: "Kalyani — Quotation v1.docx",
        snippet: "400 units @ ₹2,100 · freight extra · valid 30 days",
        meta: "Drive · 14 Jan",
      },
      {
        n: 2,
        source: "google",
        title: "Re: Revised pricing — Kalyani",
        snippet: "“we can absorb freight and hold at ₹7,95,000”",
        meta: "Gmail · 22 Jan",
      },
      {
        n: 3,
        source: "whatsapp",
        title: "Kalyani Industries",
        snippet: "“revised number works, sending PO shortly”",
        meta: "WhatsApp · 24 Jan",
      },
    ],
  },
  {
    id: "gst",
    label: "Find a GST mismatch",
    role: "The accountant",
    roleNote:
      "Reconciling the register before filing, and looking for what quietly failed to match.",
    question: "Which March invoices have no matching GST entry?",
    answer: [
      { text: "Two. " },
      { text: "INV-2026-0341 and INV-2026-0347 ", strong: true },
      {
        text: "were raised in March but have no corresponding entry in the GST register",
      },
      { text: "", cite: 1 },
      { text: ". Both are to the same buyer, and both PDFs are missing a GSTIN on the header" },
      { text: "", cite: 2 },
      { text: " — which is the likeliest reason they never got picked up." },
    ],
    sources: [
      {
        n: 1,
        source: "tally",
        title: "GST register · March 2026",
        snippet: "41 sales vouchers · 39 matched · 2 unmatched",
        meta: "Tally · 31 min ago",
      },
      {
        n: 2,
        source: "google",
        title: "INV-2026-0347.pdf",
        snippet: "Buyer GSTIN field blank · place of supply not set",
        meta: "Drive · 18 Mar",
      },
    ],
  },
]
