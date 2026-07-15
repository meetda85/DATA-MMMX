const CACHE_NAME = 'mmmx-monitor-v2';
const ASSETS = [
  '/',
  '/index.html',
  '/style.css?v=2',
  '/app.js?v=2',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/version.json'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  // Evitar interceptar llamadas a la API local
  if (e.request.url.includes('/api/')) {
    return;
  }
  
  // Estrategia: Network-First (Red primero, luego Caché como respaldo offline)
  e.respondWith(
    fetch(e.request)
      .then((response) => {
        // Guardar en caché si la respuesta es válida y del mismo origen
        if (response && response.status === 200 && response.type === 'basic') {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(e.request, responseToCache);
          });
        }
        return response;
      })
      .catch(() => {
        // Si no hay red, servir desde la caché
        return caches.match(e.request);
      })
  );
});
