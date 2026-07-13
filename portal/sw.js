/* Minimal service worker — network-first for shell, cache only as offline fallback */
const CACHE = "cctv-portal-v1.5.1";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/assets/logo.png",
  "/assets/icon-192.png",
  "/assets/icon-512.png",
  "/assets/favicon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Never touch API / health / frigate proxies
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/health/") ||
    url.pathname.startsWith("/cafe/") ||
    url.pathname.startsWith("/center11/")
  ) {
    return;
  }
  // Network-first: always try fresh, fall back to cache when offline
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});
