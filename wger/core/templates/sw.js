const CACHE_NAME = 'onyx-cache-v4';
const ASSETS_TO_CACHE = [
  '/',
  '/static/images/logos/logo-192.png',
  '/static/images/logos/logo-512.png',
  '/static/images/favicon.png',
  '/static/js/muscle_highlight.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      await Promise.allSettled(
        ASSETS_TO_CACHE.map(async url => {
          try {
            const response = await fetch(url, { cache: 'no-cache' });
            if (response && response.ok) {
              await cache.put(url, response);
            }
          } catch (err) {
            console.warn('[SW] Non-critical cache skip for:', url, err);
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
  const reqUrl = new URL(event.request.url);

  // Ignore cross-origin requests (CDNs, Google Fonts, etc.)
  if (reqUrl.origin !== self.location.origin) {
    return;
  }

  // Only handle GET requests and skip dynamic / API / auth routes
  if (
    event.request.method !== 'GET' || 
    reqUrl.pathname.startsWith('/api/') || 
    reqUrl.pathname.startsWith('/account/') ||
    reqUrl.pathname.startsWith('/user/')
  ) {
    return;
  }
  
  event.respondWith(
    fetch(event.request)
      .catch(async () => {
        const cachedResponse = await caches.match(event.request);
        if (cachedResponse) {
          return cachedResponse;
        }
        
        // Fallback for HTML document navigation if offline
        const acceptHeader = event.request.headers ? event.request.headers.get('accept') : '';
        if (acceptHeader && acceptHeader.includes('text/html')) {
          const rootCache = await caches.match('/');
          if (rootCache) {
            return rootCache;
          }
        }
        
        // Always guarantee a valid Response object (never undefined)
        return new Response('Network unavailable', {
          status: 503,
          statusText: 'Service Unavailable',
          headers: new Headers({ 'Content-Type': 'text/plain' })
        });
      })
  );
});
