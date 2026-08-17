<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

Key breaking changes already hit in this project:
- `middleware.ts` is renamed to `proxy.ts`, exported function is `proxy` not `middleware` (same NextRequest/NextResponse API otherwise).
- `params`/`searchParams`/`cookies()`/`headers()` are fully async-only — always `await` them.
<!-- END:nextjs-agent-rules -->

# shadcn components here are Base UI-backed, NOT Radix

`components.json` uses `-b base` (Base UI, `@base-ui/react`), not the default Radix primitives. This changes the composition API for every trigger-style component (Tooltip/Popover/Dialog/AlertDialog/DropdownMenu/Sheet triggers, etc.):

- Base UI has **no `asChild` prop**. Passing `asChild` + children silently fails — the trigger still renders its own default element (usually `<button>`) around your child, which causes `<button> cannot be a descendant of <button>` hydration errors when the child is also a `<Button>`.
- Instead, use the **`render` prop**: `<TooltipTrigger render={<Button variant="outline">Label</Button>} />` (a `ReactElement`, not children). Same pattern for `DialogTrigger`, `PopoverTrigger`, `AlertDialogTrigger`, `DropdownMenuTrigger`, `SheetTrigger`, etc.
- `render` also accepts a function `(props, state) => ReactElement` when you need access to the trigger's own state (e.g. open/closed).
- `Button` specifically defaults `nativeButton` to `true` and warns loudly if `render` resolves to a non-`<button>` element (e.g. a Next.js `<Link>`/`<a>` for nav CTAs). Whenever `Button`'s `render` is a link, always also pass `nativeButton={false}` — this is intentional (links should be `<a>`, not `<button>`), not a bug to work around differently.
