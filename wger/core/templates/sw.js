const CACHE_NAME = 'onyx-cache-v9';
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
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',
  'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800;900&display=swap'
];
const MAX_DYNAMIC_ENTRIES = 50;

async function trimCache(cacheName, maxItems) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length > maxItems) {
      await cache.delete(keys[0]);
      await trimCache(cacheName, maxItems);
    }
  } catch (e) {
    // Ignore cache trimming errors silently
  }
}

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      await Promise.allSettled(
        STATIC_ASSETS.map(async url => {
          try {
            const response = await fetch(url, { mode: 'cors', cache: 'reload' });
            if (response && response.ok && !response.redirected) {
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

  // 1. Static Assets (Fonts, CDN Scripts, Audio, Images, /static/, /media/) -> Stale-While-Revalidate
  const isStatic = STATIC_ASSETS.includes(req.url) || 
                   reqUrl.pathname.startsWith('/static/') || 
                   reqUrl.pathname.startsWith('/media/') ||
                   reqUrl.hostname.includes('fonts.gstatic.com') ||
                   reqUrl.hostname.includes('raw.githubusercontent.com');

  if (isStatic) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async cache => {
        const cachedResponse = await cache.match(req);

        // Fetch fresh copy from network to revalidate
        const fetchPromise = fetch(req).then(async networkResponse => {
          if (networkResponse && networkResponse.ok && !networkResponse.redirected) {
            const clone = networkResponse.clone();
            await cache.put(req, clone);
            trimCache(CACHE_NAME, MAX_DYNAMIC_ENTRIES).catch(() => {});
          }
          return networkResponse;
        }).catch(() => null);

        // Return cached immediately if available (Stale-While-Revalidate)
        if (cachedResponse) {
          event.waitUntil(fetchPromise);
          return cachedResponse;
        }

        const networkRes = await fetchPromise;
        if (networkRes) return networkRes;
        return new Response('', { status: 408, statusText: 'Request Timeout' });
      })
    );
    return;
  }

  // 2. HTML Navigation Documents -> Network-First (Do NOT cache authenticated/private HTML)
  const isHtml = req.mode === 'navigate' || (req.headers.get('accept') && req.headers.get('accept').includes('text/html'));
  if (isHtml) {
    event.respondWith(
      fetch(req).then(networkResponse => {
        // Do not cache redirects or private/authenticated HTML
        const cacheControl = networkResponse.headers.get('cache-control') || '';
        const isPrivate = cacheControl.includes('private') || cacheControl.includes('no-store') || cacheControl.includes('no-cache');

        if (networkResponse.ok && !networkResponse.redirected && !isPrivate && !reqUrl.pathname.startsWith('/workout/') && !reqUrl.pathname.startsWith('/manager/')) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(req, clone);
            trimCache(CACHE_NAME, MAX_DYNAMIC_ENTRIES).catch(() => {});
          });
        }
        return networkResponse;
      }).catch(async () => {
        // If offline and public cache hit available, return it; otherwise return offline message
        const cache = await caches.open(CACHE_NAME);
        const cachedResponse = await cache.match(req);
        if (cachedResponse) return cachedResponse;
        return new Response('<!DOCTYPE html><html><head><meta charset="utf-8"><title>Offline - Onyx</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{background:#08090A;color:#e5e2e1;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;padding:20px;}</style></head><body><div><h2 style="color:#caf300;">Dispositivo Offline</h2><p>Impossibile caricare la pagina richiesta senza connessione internet.</p></div></body></html>', {
          status: 503,
          statusText: 'Offline',
          headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
      })
    );
  }
});
