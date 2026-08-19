import { BouncyAccordion } from "@/components/motion/bouncy-accordion"
import { Panel, SectionHead, SectionShell } from "@/components/landing/section"

/**
 * The objections this product specifically raises, answered plainly.
 *
 * Every answer here is grounded in what the system actually does — the on-prem
 * Tally agent, the inbound WhatsApp webhook, per-tenant keys, the admin/member
 * boundary. Nothing is aspirational, and nothing claims a capability that
 * isn't built.
 */
const faqs = [
  {
    q: "Does SynQ write anything back into Tally?",
    a: "No. The agent that runs alongside Tally only pushes data out — ledgers, vouchers and GST data — and SynQ has no path back in. Nothing you see in an answer can change a book of accounts.",
  },
  {
    q: "Does my data train a model?",
    a: "No. Your content is indexed for your tenant and used to answer your questions, and nothing crosses into another business's index or into model training.",
  },
  {
    q: "What happens when the Tally machine is switched off?",
    a: "Nothing breaks. The agent pushes on roughly a 30-minute cycle and simply resumes when the machine is back; the next window catches up on what it missed. Answers stay grounded in the last data it saw, with the timestamp shown on the source.",
  },
  {
    q: "Which WhatsApp number does this read?",
    a: "The WhatsApp Business API number you connect. Messages arrive by inbound webhook and are indexed on a daily pass — personal WhatsApp accounts are not involved and cannot be connected.",
  },
  {
    q: "Who in my team can see what?",
    a: "Admins manage connectors and users. Members get chat and documents. The boundary is structural rather than a settings toggle, and every business gets its own scoped database — nothing is shared across tenants.",
  },
  {
    q: "What's actually live today?",
    a: "Google Workspace. Outlook and OneDrive, WhatsApp Business and Tally are built and in rollout — we turn them on per business during the beta rather than shipping them half-tested to everyone at once.",
  },
]

export function FaqSection() {
  return (
    <SectionShell id="faq">
      <SectionHead
        eyebrow="Questions"
        heading="The things people ask first"
        lead="Mostly about what SynQ won't do, which is the more useful half."
      />

      {/* beui bouncy-accordion, not the shadcn one — the spring on open is the
          whole reason to use a component library built around motion. It takes
          items as data rather than composed children. */}
      <Panel className="mx-auto mt-12 max-w-3xl p-2 sm:p-4">
        <BouncyAccordion
          collapsible
          items={faqs.map((faq) => ({
            id: faq.q,
            title: faq.q,
            description: faq.a,
          }))}
          classNames={{
            item: "border-border-subtle",
            trigger: "px-4 py-5",
            title: "text-[1.0625rem] font-medium",
            content: "px-4",
            description:
              "max-w-[62ch] text-[0.9375rem] leading-relaxed text-muted-foreground",
          }}
        />
      </Panel>
    </SectionShell>
  )
}
