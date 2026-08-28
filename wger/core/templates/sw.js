const CACHE_NAME = 'onyx-cache-v7';
const STATIC_ASSETS = [
  '/static/images/logos/logo-192.png',
  '/static/images/logos/logo-512.png',
  '/static/images/favicon.png',
  '/static/audio/boxing.mp3',
  '/static/audio/beep.mp3',
  '/static/audio/whistle.mp3',
  '/static/audio/alarm.mp3',
  'https://cdn.tailwindcss.com?plugins=forms,container-queries',
  'https://unpkg.com/htmx.org@1.9.10',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800;900&display=swap'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      await Promise.allSettled(
        STATIC_ASSETS.map(async url => {
          try {
            const response = await fetch(url, { mode: 'cors', cache: 'reload' });
            if (response && response.ok) {
              await cache.put(url, response);
            }
          } catch (err) {
            console.warn('[SW] Cache skip for:', url, err);
          }
        })
      );
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
  const req = event.request;
  const reqUrl = new URL(req.url);

  // Skip non-GET requests (handled by Offline Sync Queue)
  if (req.method !== 'GET') {
    return;
  }

  // Skip sensitive auth routes
  if (reqUrl.pathname.startsWith('/account/login') || reqUrl.pathname.startsWith('/account/logout')) {
    return;
  }

  // 1. Static Assets (Fonts, CDN Scripts, Audio, Images) -> Cache-First
  const isStatic = STATIC_ASSETS.includes(req.url) || 
                   reqUrl.pathname.startsWith('/static/') || 
                   reqUrl.pathname.startsWith('/media/') ||
                   reqUrl.hostname.includes('fonts.gstatic.com') ||
                   reqUrl.hostname.includes('raw.githubusercontent.com');

  if (isStatic) {
    event.respondWith(
      caches.match(req).then(cached => {
        if (cached) return cached;
        return fetch(req).then(res => {
          if (res && res.ok) {
            const clone = res.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
          }
          return res;
        }).catch(() => {
          return new Response('', { status: 408, statusText: 'Request Timeout' });
        });
      })
    );
    return;
  }

  // 2. HTML Navigation Documents -> Stale-While-Revalidate (Instant 0ms Load + Background Update)
  const isHtml = req.mode === 'navigate' || (req.headers.get('accept') && req.headers.get('accept').includes('text/html'));
  if (isHtml) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async cache => {
        const cachedResponse = await cache.match(req);

        const networkFetchPromise = fetch(req).then(networkResponse => {
          if (networkResponse && networkResponse.ok) {
            cache.put(req, networkResponse.clone());
          }
          return networkResponse;
        }).catch(err => {
          // If offline and have cache, return cache
          if (cachedResponse) return cachedResponse;
          return new Response('Network offline', { status: 503, statusText: 'Offline' });
        });

        // Return cached immediately if available, otherwise wait for network
        return cachedResponse || networkFetchPromise;
      })
    );
  }
});
