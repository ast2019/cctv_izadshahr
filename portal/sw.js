/* Offline-capable shell cache — network-first, local assets only */
const CACHE = "cctv-portal-v1.6.2";
const SHELL = [
  "/",
  "/index.html",
  "/manifest.webmanifest",
  "/css/fonts.css?v=1.6.2",
  "/css/main.css?v=1.6.2",
  "/js/app.js?v=1.6.2",
  "/js/sites.js?v=1.6.2",
  "/js/auth-config.js?v=1.6.2",
  "/js/changelog.js?v=1.6.2",
  "/js/changelog-ui.js?v=1.6.2",
  "/js/load-monitor.js?v=1.6.2",
  "/js/admin-panel.js?v=1.6.2",
  "/js/ambiance.js?v=1.6.2",
  "/fonts/Vazirmatn-Regular.woff2",
  "/fonts/Vazirmatn-Medium.woff2",
  "/fonts/Vazirmatn-SemiBold.woff2",
  "/fonts/Vazirmatn-Bold.woff2",
  "/assets/logo.png",
  "/assets/icon-192.png",
  "/assets/icon-512.png",
  "/assets/favicon.png",
  "/assets/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) =>
        Promise.all(
          SHELL.map((u) => cache.add(u).catch(() => null))
        )
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Never cache API / health / frigate proxies
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/health/") ||
    url.pathname.startsWith("/cafe/") ||
    url.pathname.startsWith("/center11/")
  ) {
    return;
  }
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((c) => c || caches.match("/index.html")))
  );
});
