/* Kill leftover service workers (e.g. Grafana when it previously bound :3000). */
self.addEventListener("install", (event) => {
  self.skipWaiting()
  event.waitUntil(Promise.resolve())
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.map((key) => caches.delete(key)))
      await self.registration.unregister()
      const clients = await self.clients.matchAll({ type: "window" })
      for (const client of clients) {
        client.navigate(client.url)
      }
    })()
  )
})
