self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))),
      self.registration.unregister(),
      self.clients.claim(),
    ])
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
