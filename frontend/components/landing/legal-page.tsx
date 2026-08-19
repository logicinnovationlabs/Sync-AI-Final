/**
 * Shell for the legal routes.
 *
 * The footer links to /privacy and /terms, so the routes have to exist. The
 * *text* is deliberately not written — inventing a privacy policy for a product
 * that reads customers' ledgers and WhatsApp threads would be exactly the kind
 * of fabricated document SUMMARY.md §7 rules out, and it would be worse than
 * having no page at all because it would look authoritative.
 *
 * Replace <LegalPlaceholder> with the reviewed copy. Nothing else changes.
 */
export function LegalPage({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="relative">
      <div className="mx-auto max-w-3xl px-6 pt-20 pb-24 lg:pt-28">
        <h1 className="font-heading text-[clamp(2.25rem,5vw,3.25rem)] leading-[1.08] font-normal tracking-[-0.02em]">
          {title}
        </h1>
        <div className="mt-10 flex flex-col gap-5 text-[1.0625rem] leading-relaxed text-muted-foreground">
          {children}
        </div>
      </div>
    </section>
  )
}

export function LegalPlaceholder({ document }: { document: string }) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-border bg-surface p-8">
      <p className="font-mono text-[0.6875rem] uppercase tracking-[0.14em] text-muted-foreground">
        Not yet written
      </p>
      <p className="mt-3 text-[1rem] leading-relaxed text-foreground">
        The {document} for SynQ AI has not been drafted. This page exists so the
        link in the footer resolves; it is not a statement of policy, and nothing
        should be inferred from it.
      </p>
      <p className="mt-3 text-[0.9375rem] leading-relaxed">
        If you need this before it&apos;s published, ask us directly — we&apos;ll
        tell you exactly what is stored, where, and for how long.
      </p>
    </div>
  )
}
