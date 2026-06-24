/**
 * sw.js — Service Worker for xstk PWA
 *
 * Strategies:
 *  - Cache First  → static assets (CSS, JS, icons, fonts)
 *  - Network First → API calls (/api/v1/*)
 *  - Offline Fallback → navigate requests fallback to /static/offline.html
 *
 * Push:
 *  - Receives VAPID push events → shows notification
 *  - Click on notification → opens the URL from payload
 */

const CACHE_VERSION = 'xstk-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;

// Assets to pre-cache on install
const PRECACHE_ASSETS = [
  '/static/offline.html',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/manifest.json',
];

// ---------------------------------------------------------------------------
// Install — pre-cache critical assets
// ---------------------------------------------------------------------------
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_ASSETS))
  );
});

// ---------------------------------------------------------------------------
// Activate — clean up old caches
// ---------------------------------------------------------------------------
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('xstk-') && k !== STATIC_CACHE)
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ---------------------------------------------------------------------------
// Fetch — routing strategy
// ---------------------------------------------------------------------------
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== self.location.origin) return;

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // API calls — Network First, no cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets (CSS, JS, images, fonts) — Cache First
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname === '/static/manifest.json'
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // HTML navigation — Network First with offline fallback
  if (request.mode === 'navigate') {
    event.respondWith(navigationWithOfflineFallback(request));
    return;
  }
});

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Not available offline', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    return await fetch(request);
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function navigationWithOfflineFallback(request) {
  try {
    return await fetch(request);
  } catch {
    const offline = await caches.match('/static/offline.html');
    return offline || new Response('<h1>Offline</h1>', {
      headers: { 'Content-Type': 'text/html' },
    });
  }
}

// ---------------------------------------------------------------------------
// Push — receive push event and show notification
// ---------------------------------------------------------------------------
self.addEventListener('push', (event) => {
  if (!event.data) return;

  let payload = {};
  try {
    payload = event.data.json();
  } catch {
    payload = { title: 'Thông báo mới', body: event.data.text(), url: '/' };
  }

  const title = payload.title || 'Khóa Tu Mùa Hè';
  const options = {
    body: payload.body || '',
    icon: payload.icon || '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    data: { url: payload.url || '/' },
    tag: payload.tag || 'xstk-notification',
    renotify: true,
    vibrate: [200, 100, 200],
    actions: [
      { action: 'open', title: 'Xem ngay' },
      { action: 'dismiss', title: 'Bỏ qua' },
    ],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// ---------------------------------------------------------------------------
// Notification click — open the correct URL
// ---------------------------------------------------------------------------
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // If app already open in a tab, focus it and navigate
      for (const client of windowClients) {
        if ('focus' in client) {
          client.focus();
          client.navigate(targetUrl);
          return;
        }
      }
      // Otherwise open a new window
      return clients.openWindow(targetUrl);
    })
  );
});
