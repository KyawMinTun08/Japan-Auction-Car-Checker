// JACC PWA Service Worker
// Version 2026.08.20-startup-recovery-v4
const CACHE_PREFIX = 'jacc-';
const CACHE_NAME = 'jacc-2026.08.20-startup-recovery-v4';
const BASE_PATH = '/Japan-Auction-Car-Checker';
const APP_SHELL = [
  BASE_PATH + '/',
  BASE_PATH + '/index.html',
  BASE_PATH + '/manifest.json',
  BASE_PATH + '/icon-192.png',
  BASE_PATH + '/icon-512.png',
  BASE_PATH + '/jdm-config.js',
  BASE_PATH + '/phase2/website_device_binding.js',
  BASE_PATH + '/assets/brand-logos/Toyota.svg',
  BASE_PATH + '/assets/brand-logos/Honda.svg',
  BASE_PATH + '/assets/brand-logos/Nissan.svg',
  BASE_PATH + '/assets/brand-logos/Mazda.svg',
  BASE_PATH + '/assets/brand-logos/Suzuki.svg',
  BASE_PATH + '/assets/brand-logos/Mitsubishi.svg',
  BASE_PATH + '/assets/brand-logos/Subaru.svg',
  BASE_PATH + '/assets/brand-logos/Volkswagen.svg'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(
        names
          .filter(name => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
          .map(name => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isBackendRequest(url) {
  return url.hostname.includes('script.google.com') ||
    url.hostname.includes('script.googleusercontent.com') ||
    url.hostname.includes('docs.google.com') ||
    url.hostname.includes('ipapi.co') ||
    url.pathname.includes('/api/jdm/lookup') ||
    url.pathname.includes('/api/jdm/explain');
}

function isRuntimeAsset(url) {
  return url.hostname.includes('fonts.googleapis.com') ||
    url.hostname.includes('fonts.gstatic.com') ||
    url.hostname.includes('cdnjs.cloudflare.com');
}

async function networkFirst(request, fallbackUrl) {
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    return (await caches.match(request)) || (fallbackUrl && await caches.match(fallbackUrl)) || Response.error();
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(response => {
      if (response && response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);
  return cached || (await network) || Response.error();
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    const cache = await caches.open(CACHE_NAME);
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (isBackendRequest(url)) return;

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, BASE_PATH + '/index.html'));
    return;
  }

  if (isRuntimeAsset(url)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(staleWhileRevalidate(request));
  }
});
