const CACHE_NAME = 'metaedu-v3';
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/telematica.html',
  '/software.html',
  '/preparatoria.html',
  '/campus-virtual.html',
  '/portafolio-completo.html',
  '/style.css',
  '/script.js',
  '/manifest.json',
  '/assets/logo_white.png',
  '/assets/icon-192.png',
  '/assets/icon-512.png',
  '/assets/axolotl-waving.png',
  '/assets/axo-polo-waving.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      await Promise.allSettled(
        ASSETS_TO_CACHE.map((asset) => cache.add(asset))
      );
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') {
    return;
  }

  const requestUrl = new URL(event.request.url);
  const sameOrigin = requestUrl.origin === self.location.origin;
  const isAdminAsset = sameOrigin && (
    requestUrl.pathname === '/admin.html' ||
    requestUrl.pathname === '/assets/admin.js' ||
    requestUrl.pathname === '/assets/admin.css'
  );

  if (isAdminAsset) {
    event.respondWith(
      fetch(event.request).catch(async () => {
        const cachedResponse = await caches.match(event.request);
        return cachedResponse || new Response('Offline', {
          status: 503,
          statusText: 'Offline'
        });
      })
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then(async (cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }

      try {
        const networkResponse = await fetch(event.request);

        if (sameOrigin && networkResponse && networkResponse.ok) {
          const cache = await caches.open(CACHE_NAME);
          cache.put(event.request, networkResponse.clone());
        }

        return networkResponse;
      } catch (error) {
        if (event.request.mode === 'navigate') {
          const fallback = await caches.match('/index.html');
          if (fallback) {
            return fallback;
          }
        }

        return new Response('Offline', {
          status: 503,
          statusText: 'Offline'
        });
      }
    })
  );
});
