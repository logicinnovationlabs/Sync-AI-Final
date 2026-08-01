import { HardDrive, Mail, MessageCircle, Receipt } from "lucide-react"

export type ConnectorSourceType = "google" | "outlook" | "whatsapp" | "tally"

export type ConnectionModel = "oauth" | "webhook" | "agent-token"

export interface ConnectorMeta {
  source: ConnectorSourceType
  name: string
  shortLabel: string
  description: string
  connectionModel: ConnectionModel
  /** How the connection is established, in the user's words. */
  handshake: string
  /** Real ingestion cadence, per PRODUCT.md. */
  cadence: string
  icon: typeof Mail
  /** Whether the backend has a working integration for this source today. */
  available: boolean
}

export const CONNECTORS: ConnectorMeta[] = [
  {
    source: "google",
    name: "Google Workspace",
    shortLabel: "Google",
    description: "Drive documents and Gmail threads, indexed continuously.",
    connectionModel: "oauth",
    handshake: "OAuth consent",
    cadence: "Polled every ~3 min",
    icon: HardDrive,
    available: true,
  },
  {
    source: "outlook",
    name: "Outlook & OneDrive",
    shortLabel: "Outlook",
    description: "Mail and files from Microsoft 365, kept in sync.",
    connectionModel: "oauth",
    handshake: "OAuth consent",
    cadence: "Polled every ~3 min",
    icon: Mail,
    available: false,
  },
  {
    source: "whatsapp",
    name: "WhatsApp Business",
    shortLabel: "WhatsApp",
    description: "Customer conversations, searchable alongside everything else.",
    connectionModel: "webhook",
    handshake: "Inbound webhook",
    cadence: "Indexed daily",
    icon: MessageCircle,
    available: false,
  },
  {
    source: "tally",
    name: "Tally ERP",
    shortLabel: "Tally",
    description: "Ledgers, vouchers, and GST data from an on-prem agent.",
    connectionModel: "agent-token",
    handshake: "Signed on-prem agent",
    cadence: "Pushed every ~30 min",
    icon: Receipt,
    available: false,
  },
]
