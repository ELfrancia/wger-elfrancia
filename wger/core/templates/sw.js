{% load static %}
const CACHE_NAME = 'onyx-cache-v13';

// Assets the app cannot work without, and whose absence does not look like an
// absence. Without htmx every hx-post control is inert while the page still
// renders perfectly, so it reads as "the buttons are broken". Without the icon
// font every material-symbols span shows its ligature as literal text - "add",
// "check", "fitness_center" - so it reads as a broken app rather than a
// missing font. All of these are same-origin now (they used to be CDN URLs),
// so caching them can no longer fail because a third party is unreachable.
const CRITICAL_ASSETS = [
  '{% static "js/vendor/htmx-1.9.10.min.js" %}',
  '{% static "css/tailwind-compiled.css" %}',
  '{% static "css/vendor/fonts.css" %}',
  '{% static "fonts/vendor/material-symbols-outlined.woff2" %}'
];

const STATIC_ASSETS = CRITICAL_ASSETS.concat([
  '{% static "js/vendor/chart-4.5.1.min.js" %}',
  '{% static "fonts/vendor/inter-latin.woff2" %}',
  '{% static "fonts/vendor/inter-latin-ext.woff2" %}',
  '{% static "fonts/vendor/outfit-latin.woff2" %}',
  '{% static "fonts/vendor/outfit-latin-ext.woff2" %}',
  '/static/images/logos/logo-192.png',
  '/static/images/logos/logo-512.png',
  '/static/images/favicon.png',
  '/static/audio/boxing.mp3',
  '/static/audio/beep.mp3',
  '/static/audio/whistle.mp3',
  '/static/audio/alarm.mp3'
]);

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async cache => {
      await Promise.allSettled(
        STATIC_ASSETS.map(async url => {
          try {
            const response = await fetch(url, { mode: 'cors', cache: 'reload' });
            if (response && response.ok) {
              await cache.put(url, response);
            } else if (CRITICAL_ASSETS.includes(url)) {
              console.error('[SW] Critical asset not cached:', url, response && response.status);
            }
          } catch (err) {
            if (CRITICAL_ASSETS.includes(url)) {
              console.error('[SW] Critical asset failed:', url, err);
            } else {
              console.warn('[SW] Cache skip for:', url, err);
            }
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

  // 1. Immutable static assets (Fonts, CDN scripts, audio, Django /static/) -> Cache-First
  const isStatic = STATIC_ASSETS.includes(req.url) ||
                   reqUrl.pathname.startsWith('/static/') ||
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

  // 2. User media (avatars, condition photos) -> Network-First (they change / get deleted)
  if (reqUrl.pathname.startsWith('/media/')) {
    event.respondWith(
      fetch(req).then(res => {
        if (res && res.ok) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return res;
      }).catch(() => caches.match(req).then(c => c || new Response('', { status: 504 })))
    );
    return;
  }

  // 3. HTML navigation documents -> Network-First (deployed fixes must land immediately)
  const isHtml = req.mode === 'navigate' || (req.headers.get('accept') && req.headers.get('accept').includes('text/html'));
  if (isHtml) {
    event.respondWith(
      fetch(req).then(networkResponse => {
        if (networkResponse && networkResponse.ok) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return networkResponse;
      }).catch(async () => {
        const cached = await caches.match(req);
        return cached || new Response('Network offline', { status: 503, statusText: 'Offline' });
      })
    );
  }
});
