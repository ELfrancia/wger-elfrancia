const CACHE_NAME = 'wger-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/images/logos/logo-192.png',
  '/static/images/logos/logo-512.png',
  '/static/images/favicon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(ASSETS_TO_CACHE);
      })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  // Let the browser handle foreign domains, API, and authentication/POST requests naturally.
  if (event.request.method !== 'GET' || event.request.url.includes('/api/v2/') || event.request.url.includes('/account/')) {
    return;
  }
  
  event.respondWith(
    fetch(event.request)
      .catch(() => {
        return caches.match(event.request)
          .then(response => {
            if (response) {
              return response;
            }
            // Fallback for document navigation if offline
            if (event.request.headers.get('accept').includes('text/html')) {
              return caches.match('/');
            }
          });
      })
  );
});
