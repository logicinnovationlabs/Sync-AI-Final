"use client"

import { ConnectorCard } from "@/components/connectors/connector-card"
import { CONNECTORS } from "@/lib/connectors"

/**
 * The list lives on the client, not in the page.
 *
 * `ConnectorMeta.icon` is a lucide component — a function — and functions can't
 * be serialised across the RSC boundary. Mapping `CONNECTORS` inside the server
 * page and handing whole objects to the card crashed the route with "Functions
 * cannot be passed directly to Client Components". Importing the array here
 * keeps it entirely on one side of the boundary.
 */
export function ConnectorList() {
  return (
    <ul className="mx-auto grid w-full max-w-5xl gap-4 px-6 py-8 md:grid-cols-2">
      {CONNECTORS.map((connector, index) => (
        <ConnectorCard
          key={connector.source}
          connector={connector}
          index={index}
        />
      ))}
    </ul>
  )
}
