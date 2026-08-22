import path from "node:path"
import { fileURLToPath } from "node:url"
import type { NextConfig } from "next"

const frontendRoot = path.dirname(fileURLToPath(import.meta.url))

const nextConfig: NextConfig = {
  // Pin to this package. A lockfile in C:\Users\ROHAN made Turbopack
  // treat the whole home directory as the app and freeze page compiles.
  // Only apply locally — on Vercel the app root is already `frontend/`.
  // Only apply locally — on Vercel the app root is already `frontend/`.
  ...(process.env.VERCEL ? {} : { outputFileTracingRoot: frontendRoot }),
}

export default nextConfig
