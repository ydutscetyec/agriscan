/* AGRISCAN service worker, v3.
 *
 * v3 (p21): cache names bumped so the first visit after this update clears the v2
 * caches, including the Google Fonts setup that is no longer used. Fonts are now build
 * assets under /assets/ and are cached by the rule below like any other asset.
 *
 * v1 cached every same-origin request cache-first. In development those requests are the
 * app's own source modules, so an updated app kept being served from the old cache. With
 * the API now proxied under /api on the same origin, v1 would also have cached live data.
 *
 * v2 rules:
 *   /assets/*               content-hashed build files: cache-first, safe forever
 *   /api/recommendations/*  network-first, last approved copy kept for offline reading
 *   /api/* (anything else)  never cached. Stale crop results shown as current are worse
 *                           than an honest "cannot reach the server".
 *   page navigations        network-first, cached shell as the offline fallback
 */

const SHELL_CACHE = 'agriscan-shell-v3'
const ASSET_CACHE = 'agriscan-assets-v3'
const API_CACHE = 'agriscan-recs-v3'
const KEEP = [SHELL_CACHE, ASSET_CACHE, API_CACHE]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((c) => c.addAll(['/', '/index.html'])).then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !KEEP.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

function networkFirst(request, cacheName) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone()
        caches.open(cacheName).then((c) => c.put(request, copy))
      }
      return response
    })
    .catch(() => caches.match(request))
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  if (url.pathname.startsWith('/api/recommendations/')) {
    event.respondWith(networkFirst(request, API_CACHE))
    return
  }
  if (url.pathname.startsWith('/api/')) return // live data: straight to the network

  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone()
          caches.open(ASSET_CACHE).then((c) => c.put(request, copy))
        }
        return response
      })),
    )
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/index.html')),
    )
  }
})
