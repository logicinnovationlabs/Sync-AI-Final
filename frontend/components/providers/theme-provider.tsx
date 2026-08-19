"use client"

import { ThemeProvider as NextThemesProvider } from "next-themes"
import type { ComponentProps } from "react"

export function ThemeProvider({
  children,
  ...props
}: ComponentProps<typeof NextThemesProvider>) {
  // next-themes injects an inline <script> to apply the stored theme before
  // paint. React 19 warns on client-rendered JS <script> tags. A data-block
  // MIME type is identical on server and client, so it neither warns nor
  // hydrates differently. Theme is forced to light in the root layout.
  return (
    <NextThemesProvider
      {...props}
      scriptProps={{ type: "application/json" }}
    >
      {children}
    </NextThemesProvider>
  )
}
