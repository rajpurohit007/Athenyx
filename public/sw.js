// E:\shopify-mern-project\public\sw.js (Verified and Correct)

console.log('Service Worker Registered!');

self.addEventListener('push', function(event) {
    const data = event.data.json();
    console.log('Push received:', data);

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.icon,
        vibrate: [200, 100, 200],
        data: {
            url: data.url
        }
    };

    // Show the notification
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Optional: Handle clicks on the notification
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    const urlToOpen = event.notification.data.url || '/';

    event.waitUntil(
        clients.openWindow(urlToOpen)
    );
});
