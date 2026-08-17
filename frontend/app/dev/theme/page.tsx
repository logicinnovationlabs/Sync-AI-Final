import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover"
import { Logo } from "@/components/brand/logo"
import { Haze } from "@/components/brand/haze"

const neutralSteps = [
  25, 50, 100, 150, 200, 300, 400, 500, 600, 700, 800, 900, 950,
]
const hazeSteps = [
  "haze-saffron",
  "haze-amber",
  "haze-periwinkle",
  "haze-violet",
  "ink-blue",
]
const contrastPairs = [
  {
    label: "Body on paper",
    bg: "var(--background)",
    fg: "var(--foreground)",
    note: "fg / bg",
  },
  {
    label: "Muted metadata",
    bg: "var(--background)",
    fg: "var(--muted-foreground)",
    note: "muted-fg / bg",
  },
  {
    label: "Primary button label",
    bg: "var(--primary)",
    fg: "var(--primary-foreground)",
    note: "primary-fg / primary",
  },
  {
    label: "Card body",
    bg: "var(--card)",
    fg: "var(--card-foreground)",
    note: "card-fg / card",
  },
  {
    label: "Sidebar item",
    bg: "var(--sidebar)",
    fg: "var(--sidebar-foreground)",
    note: "sidebar-fg / sidebar",
  },
  {
    label: "Citation mark",
    bg: "color-mix(in oklch, var(--primary), transparent 88%)",
    fg: "var(--primary)",
    note: "primary / primary-12",
  },
]
const statusTokens = [
  { name: "success", label: "Success" },
  { name: "warning", label: "Warning" },
  { name: "info", label: "Info" },
  { name: "destructive", label: "Destructive" },
] as const

function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium">{title}</h2>
      {children}
    </section>
  )
}

export default function DevThemePage() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-12 flex flex-col gap-12">
      <header className="flex items-center justify-between">
        <div>
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
            SynQ AI · Design Tokens
          </p>
          <h1 className="text-2xl font-semibold">Theme sanity check</h1>
        </div>
      </header>

      <Section title="Neutral scale">
        <div className="flex flex-wrap gap-1">
          {neutralSteps.map((step) => (
            <div key={step} className="flex flex-col items-center gap-1 min-w-14">
              <div
                className="size-12 rounded-md border border-border"
                style={{ background: `var(--neutral-${step})` }}
              />
              <span className="font-mono text-[10px] text-muted-foreground">
                {step}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Haze stops">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-1">
            {hazeSteps.map((token) => (
              <div
                key={token}
                className="flex flex-col items-center gap-1 min-w-16"
              >
                <div
                  className="size-12 rounded-md border border-border"
                  style={{ background: `var(--${token})` }}
                />
                <span className="font-mono text-[10px] text-muted-foreground">
                  {token.replace("haze-", "")}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Brand">
        <div className="flex flex-wrap items-center gap-8">
          <Logo size="lg" />
          <Logo />
          <Logo size="sm" />
          <Logo markOnly />
        </div>
        <div className="relative isolate h-40 overflow-hidden rounded-2xl border border-border">
          <Haze height={160} />
        </div>
      </Section>

      <Section title="Contrast pairs">
        <p className="text-xs text-muted-foreground">
          Every pair below carries body text or a control label, so each must
          clear 4.5:1 in both themes. The primary swaps ends of the ramp
          between light and dark — that is what keeps this table passing.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {contrastPairs.map((pair) => (
            <div
              key={pair.label}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5"
              style={{ background: pair.bg, color: pair.fg }}
            >
              <span className="text-sm">{pair.label}</span>
              <span className="font-mono text-[10px] opacity-70">
                {pair.note}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Semantic status">
        <div className="flex gap-3">
          {statusTokens.map((t) => (
            <div
              key={t.name}
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2"
              style={{
                background: `color-mix(in oklch, var(--${t.name}), transparent 85%)`,
              }}
            >
              <span
                className="size-2.5 rounded-full"
                style={{ background: `var(--${t.name})` }}
              />
              <span className="text-sm">{t.label}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typography">
        <div className="flex flex-col gap-2">
          <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
            Eyebrow label · monospace uppercase
          </p>
          <p className="font-heading text-4xl font-normal tracking-[-0.018em]">
            Ask your business anything. — display face, Newsreader
          </p>
          <p className="text-3xl font-semibold tracking-tight">
            Ask your business anything. — body face, Geist Sans
          </p>
          <p className="text-base">
            Chat message body — text-base, Geist Sans.
          </p>
          <p className="text-sm text-muted-foreground">
            Body default / table cell — text-sm.
          </p>
          <p className="text-xs text-muted-foreground">
            Metadata / timestamp — text-xs.
          </p>
          <p className="font-mono text-sm">
            TXN-2026-000481 · Geist Mono for ledger &amp; structured data.
          </p>
        </div>
      </Section>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Section>

      <Section title="Card, badge, avatar, alert">
        <div className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Google Workspace</CardTitle>
              <CardDescription>Last synced 3 minutes ago</CardDescription>
            </CardHeader>
            <CardContent className="flex items-center gap-2">
              <Badge>Connected</Badge>
              <Badge variant="secondary">124 documents</Badge>
            </CardContent>
            <CardFooter className="flex items-center gap-2">
              <Avatar className="size-6">
                <AvatarFallback>SQ</AvatarFallback>
              </Avatar>
              <span className="text-xs text-muted-foreground">
                synq-demo.myshopify
              </span>
            </CardFooter>
          </Card>

          <Alert>
            <AlertTitle>No fabricated data</AlertTitle>
            <AlertDescription>
              Empty states must never show invented numbers or sample
              conversations.
            </AlertDescription>
          </Alert>
        </div>
      </Section>

      <Section title="Form controls">
        <div className="flex flex-col gap-3 max-w-sm">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dev-email">Email</Label>
            <Input id="dev-email" placeholder="you@company.com" />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="dev-switch" />
            <Label htmlFor="dev-switch">Stream responses</Label>
          </div>
        </div>
      </Section>

      <Section title="Tabs, tooltip, popover">
        <div className="flex flex-col gap-4">
          <Tabs defaultValue="chat">
            <TabsList>
              <TabsTrigger value="chat">Chat</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="connectors">Connectors</TabsTrigger>
            </TabsList>
            <TabsContent value="chat" className="text-sm text-muted-foreground">
              Streaming, source-cited answers.
            </TabsContent>
            <TabsContent
              value="documents"
              className="text-sm text-muted-foreground"
            >
              Browse indexed documents by source.
            </TabsContent>
            <TabsContent
              value="connectors"
              className="text-sm text-muted-foreground"
            >
              Google, Outlook, WhatsApp, Tally.
            </TabsContent>
          </Tabs>

          <div className="flex items-center gap-3">
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button variant="outline" size="sm">
                    Hover me
                  </Button>
                }
              />
              <TooltipContent>Tooltip content</TooltipContent>
            </Tooltip>

            <Popover>
              <PopoverTrigger
                render={
                  <Button variant="outline" size="sm">
                    Open popover
                  </Button>
                }
              />
              <PopoverContent className="text-sm">
                Citation card would render here.
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </Section>

      <Section title="Loading skeleton">
        <div className="flex flex-col gap-2 max-w-sm">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </Section>

      <Separator />

      <p className="text-xs text-muted-foreground pb-8">
        Toggle the theme above and confirm every token below reads correctly
        in both light and dark — nothing here should look like unstyled or
        default shadcn.
      </p>
    </div>
  )
}
