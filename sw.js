// JACC PWA Service Worker
// Version 1.0.0

const CACHE_NAME = 'jacc-v1';
const BASE_PATH = '/Japan-Auction-Car-Checker';

// Files to cache on install (app shell)
const STATIC_ASSETS = [
  BASE_PATH + '/',
  BASE_PATH + '/index.html',
  BASE_PATH + '/manifest.json',
  BASE_PATH + '/icon-192.png',
  BASE_PATH + '/icon-512.png'
];

// Install event - cache the app shell
self.addEventListener('install', event => {
  console.log('[SW] Install');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching app shell');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
      .catch(err => console.warn('[SW] Cache failed:', err))
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('[SW] Activate');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            console.log('[SW] Removing old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - smart caching strategy
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // Skip non-GET requests
  if (event.request.method !== 'GET') return;
  
  // Google Apps Script / Sheets API calls - NETWORK ONLY (always fresh data)
  if (url.hostname.includes('script.google.com') ||
      url.hostname.includes('googleusercontent.com') ||
      url.hostname.includes('docs.google.com') ||
      url.hostname.includes('ipapi.co')) {
    // Let browser handle normally - don't cache API calls
    return;
  }
  
  // CDN resources (fonts, chart.js) - CACHE FIRST
  if (url.hostname.includes('fonts.googleapis.com') ||
      url.hostname.includes('fonts.gstatic.com') ||
      url.hostname.includes('cdnjs.cloudflare.com')) {
    event.respondWith(
      caches.match(event.request).then(response => {
        return response || fetch(event.request).then(netResp => {
          return caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, netResp.clone());
            return netResp;
          });
        });
      })
    );
    return;
  }
  
  // App shell - NETWORK FIRST, fallback to cache (offline support)
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        if (response && response.status === 200) {
          const respClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, respClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Offline - try cache
        return caches.match(event.request).then(cached => {
          return cached || caches.match(BASE_PATH + '/index.html');
        });
      })
  );
});
