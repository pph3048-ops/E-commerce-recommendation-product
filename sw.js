// SmartShop Service Worker — Cache-first for static assets, network-first for API
const CACHE_NAME    = 'smartshop-v1';
const STATIC_ASSETS = ['/', '/index.html'];

// Install: cache shell
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(() => {}))
  );
});

// Activate: purge old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch strategy:
// • API calls   → network-first (fresh data, fallback to cache)
// • Static JS/CSS/images → cache-first
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin requests
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API: network-first
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/recommend') ||
      url.pathname.startsWith('/trending') || url.pathname.startsWith('/top-rated') ||
      url.pathname.startsWith('/search') || url.pathname.startsWith('/wishlist') ||
      url.pathname.startsWith('/interact') || url.pathname.startsWith('/product')) {
    event.respondWith(
      fetch(request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Static assets: cache-first
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(res => {
        if (res && res.status === 200) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(request, clone));
        }
        return res;
      });
    })
  );
});

// Background sync placeholder for offline actions
self.addEventListener('sync', event => {
  if (event.tag === 'sync-interactions') {
    // Future: replay queued interactions when back online
  }
});
