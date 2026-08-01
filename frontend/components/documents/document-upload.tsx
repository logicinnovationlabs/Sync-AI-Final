"use client"

import { useState } from "react"
import { FileUpload, type FileUploadItem } from "@/components/motion/file-upload"

/**
 * Upload.
 *
 * Everything here is real except the POST — there is no upload or ingest
 * endpoint on the backend (`app/main.py` mounts auth, oauth, me, admin,
 * connectors and webhooks only). Drag-and-drop, the queue, sizes and removal
 * all work; the files stay in memory.
 *
 * `FileUpload` is run **controlled** so every item is pinned to `queued`.
 * Uncontrolled, it marks additions as `uploading` and walks a progress bar to
 * "Uploaded" — which would be the screen asserting that something was indexed
 * when nothing left the browser. "Queued" is the true state, and the line
 * underneath says why it stays there.
 */
export function DocumentUpload() {
  const [items, setItems] = useState<FileUploadItem[]>([])

  return (
    <div className="flex flex-col gap-2.5">
      <FileUpload
        multiple
        value={items}
        onValueChange={(next) =>
          setItems(next.map((item) => ({ ...item, status: "queued", progress: 0 })))
        }
        title="Add documents"
        description="Drop files here, or browse. PDFs, spreadsheets, documents and images."
        accept=".pdf,.csv,.xlsx,.xls,.doc,.docx,.txt,.png,.jpg,.jpeg"
      />

      {items.length > 0 && (
        <p className="px-1 text-[0.6875rem] text-muted-foreground">
          Queued in the browser only — the ingest endpoint isn&apos;t built yet,
          so nothing has been uploaded or indexed.
        </p>
      )}
    </div>
  )
}
