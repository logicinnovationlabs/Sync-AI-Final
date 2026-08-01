import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";
import { MotionConfig } from "motion/react";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Display face for headings. A serif was right the first time — the failure
// was setting it semibold, which is what read as newspaper masthead. Set at
// 400 and large, it reads elegant and calm instead.
const newsreader = Newsreader({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  display: "swap",
});

// NEXT_PUBLIC_SITE_URL keeps the canonical origin out of the source; the
// localhost fallback is only for dev, where relative OG URLs are fine anyway.
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const description =
  "Every answer comes with its source. SynQ reads your Drive, inbox, WhatsApp Business chats and Tally ledgers as one, and points every line back to the record it came from.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "SynQ AI — Every answer comes with its source",
    template: "%s · SynQ AI",
  },
  description,
  applicationName: "SynQ AI",
  keywords: [
    "Tally ERP search",
    "WhatsApp Business search",
    "Google Workspace search",
    "Indian SMB",
    "cited answers",
    "enterprise search",
  ],
  openGraph: {
    type: "website",
    url: siteUrl,
    siteName: "SynQ AI",
    title: "SynQ AI — Every answer comes with its source",
    description,
  },
  twitter: {
    card: "summary_large_image",
    title: "SynQ AI — Every answer comes with its source",
    description,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable} antialiased`}
      suppressHydrationWarning
    >
      {/* min-h-screen, not h-full on <html> + min-h-full here. That pair
          pinned the document height to the viewport, which is what stopped
          Lenis from scrolling past the fold. */}
      <body className="flex min-h-screen flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem={false}
          disableTransitionOnChange
        >
          <MotionConfig reducedMotion="user">
            <QueryProvider>
              <TooltipProvider delay={150}>
                {children}
                <Toaster />
              </TooltipProvider>
            </QueryProvider>
          </MotionConfig>
        </ThemeProvider>
      </body>
    </html>
  );
}
