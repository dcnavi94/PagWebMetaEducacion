const CACHE_NAME = 'metaedu-v1';
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
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
