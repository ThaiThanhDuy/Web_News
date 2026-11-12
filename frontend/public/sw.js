/* Tech Digest service worker.
 *
 * Registered as /sw.js?api=<backend origin>[&dev=1]. In dev mode it only
 * handles push notifications and caches nothing (Next dev chunks aren't
 * content-hashed, caching them would serve stale code).
 *
 * Strategies (production):
 *  - Page navigations ........ network-first → cached page → /offline
 *  - /_next/static, icons .... cache-first (filenames are content-hashed)
 *  - Backend /api/* .......... network-first → last cached response
 *  - Images (thumbnails) ..... stale-while-revalidate, capped entry count
 *
 * Never cached: /api/push/* (per-browser state, always from the server).
 *
 * Bump VERSION to invalidate every cache on the next deploy.
 */
const VERSION = "v3";
const PARAMS = new URL(self.location.href).searchParams;
const DEV = PARAMS.get("dev") === "1";
const API_BASE = PARAMS.get("api") || "";
const PRECACHE = `precache-${VERSION}`;
const PAGES = `pages-${VERSION}`;
const STATIC = `static-${VERSION}`;
const API = `api-${VERSION}`;
const IMAGES = `images-${VERSION}`;
const CURRENT = [PRECACHE, PAGES, STATIC, API, IMAGES];

const OFFLINE_URL = "/offline";
const PRECACHE_URLS = [
  OFFLINE_URL,
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

const MAX_ENTRIES = { [PAGES]: 40, [API]: 60, [IMAGES]: 150 };

self.addEventListener("install", (event) => {
  if (DEV) {
    event.waitUntil(self.skipWaiting());
    return;
  }
  event.waitUntil(
    caches
      .open(PRECACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => DEV || !CURRENT.includes(k)).map((k) => caches.delete(k)));
      if (self.registration.navigationPreload) {
        await self.registration.navigationPreload.enable();
      }
      await self.clients.claim();
    })()
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

async function trim(cacheName) {
  const max = MAX_ENTRIES[cacheName];
  if (!max) return;
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  // Cache keys are kept in insertion order, so the oldest go first.
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function put(cacheName, request, response) {
  if (!response || !(response.ok || response.type === "opaque")) return;
  const cache = await caches.open(cacheName);
  await cache.put(request, response);
  trim(cacheName);
}

async function networkFirst(event, cacheName, fallbackUrl) {
  const { request } = event;
  try {
    const preloaded = request.mode === "navigate" ? await event.preloadResponse : undefined;
    const response = preloaded || (await fetch(request));
    event.waitUntil(put(cacheName, request, response.clone()));
    return response;
  } catch (err) {
    const cached = await caches.match(request, { ignoreVary: true });
    if (cached) return cached;
    if (fallbackUrl) {
      const fallback = await caches.match(fallbackUrl);
      if (fallback) return fallback;
    }
    throw err;
  }
}

async function cacheFirst(event, cacheName) {
  const cached = await caches.match(event.request);
  if (cached) return cached;
  const response = await fetch(event.request);
  event.waitUntil(put(cacheName, event.request, response.clone()));
  return response;
}

async function staleWhileRevalidate(event, cacheName) {
  const cached = await caches.match(event.request);
  const network = fetch(event.request)
    .then((response) => {
      event.waitUntil(put(cacheName, event.request, response.clone()));
      return response;
    })
    .catch(() => cached);
  return cached || network;
}

self.addEventListener("fetch", (event) => {
  if (DEV) return;
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.protocol !== "http:" && url.protocol !== "https:") return;
  const sameOrigin = url.origin === self.location.origin;

  // Never touch Next.js dev / HMR traffic.
  if (sameOrigin && url.pathname.startsWith("/_next/webpack-hmr")) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(event, PAGES, OFFLINE_URL));
    return;
  }

  // React Server Component payloads used for client-side navigation.
  if (sameOrigin && (request.headers.get("RSC") === "1" || url.searchParams.has("_rsc"))) {
    event.respondWith(networkFirst(event, PAGES));
    return;
  }

  if (sameOrigin && (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/"))) {
    event.respondWith(cacheFirst(event, STATIC));
    return;
  }

  // Per-browser push state and event beacons: always straight to the server.
  if (url.pathname.startsWith("/api/push") || url.pathname.startsWith("/api/events")) return;

  // Backend API (may live on another origin, e.g. http://localhost:8000).
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(event, API));
    return;
  }

  if (request.destination === "image" || (sameOrigin && url.pathname.startsWith("/_next/image"))) {
    event.respondWith(staleWhileRevalidate(event, IMAGES));
    return;
  }
});

// ------------------------------------------------------------- Web Push

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "Tech Digest";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      icon: data.icon || "/icons/icon-192.png",
      tag: data.tag,
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const itemId = Number(String(event.notification.tag || "").replace(/^item-/, ""));
  if (API_BASE && Number.isInteger(itemId) && itemId > 0) {
    // Anonymous "push opened" counter (engagement signal for ranking).
    fetch(`${API_BASE}/api/events`, {
      method: "POST",
      body: JSON.stringify({ events: [{ type: "push_open", item_id: itemId }] }),
      headers: { "Content-Type": "text/plain" },
      keepalive: true,
    }).catch(() => {});
  }
  const target = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      // Same-origin target and an app window open: reuse it.
      if (target.origin === self.location.origin) {
        for (const client of windows) {
          if ("focus" in client) {
            await client.navigate(target.href).catch(() => {});
            return client.focus();
          }
        }
      }
      return self.clients.openWindow(target.href);
    })()
  );
});

// The push service rotated the subscription: re-register it with the same
// topics so notifications keep arriving without the user doing anything.
self.addEventListener("pushsubscriptionchange", (event) => {
  if (!API_BASE) return;
  event.waitUntil(
    (async () => {
      const old = event.oldSubscription;
      let topics = [];
      if (old) {
        const res = await fetch(`${API_BASE}/api/push/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: old.endpoint }),
        }).catch(() => null);
        if (res && res.ok) topics = (await res.json()).topics || [];
      }
      const config = await fetch(`${API_BASE}/api/push/config`).then((r) => r.json());
      if (!config.enabled) return;
      const sub =
        event.newSubscription ||
        (await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(config.public_key),
        }));
      await fetch(`${API_BASE}/api/push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subscription: sub.toJSON(), topics }),
      });
      if (old) {
        await fetch(`${API_BASE}/api/push/unsubscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: old.endpoint }),
        }).catch(() => {});
      }
    })()
  );
});

function urlBase64ToUint8Array(base64) {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
