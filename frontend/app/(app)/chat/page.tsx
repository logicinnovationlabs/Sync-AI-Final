import type { Metadata } from "next"
import { ChatView } from "@/components/chat/chat-view"

export const metadata: Metadata = {
  title: "Chat",
}

// No PageHeader here — a conversation surface owns its full height, and the
// app shell's bar already says where you are.
export default function ChatPage() {
  return <ChatView />
}
