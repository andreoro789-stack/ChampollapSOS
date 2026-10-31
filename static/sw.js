const CACHE_NAME = 'champollap-sos-v1';

self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', (e) => {
  // Manejo de red directo para asegurar sincronización en tiempo real
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

// Manejar el clic en las notificaciones flotantes de emergencia (Segundo plano / Almuerzo)
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes('/admin') && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('/admin');
            }
        })
    );
});