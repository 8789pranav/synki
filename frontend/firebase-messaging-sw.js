// Firebase Messaging Service Worker
// This handles push notifications when the app is in the background

importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-messaging-compat.js');

// Firebase config will be injected from the main app
// For now, use placeholder - update these with your actual Firebase config
const firebaseConfig = {
    apiKey: "AIzaSyCkrsx1yzszd4hSSnqEHvdUmik8eae2D7E",
    authDomain: "synciki.firebaseapp.com",
    projectId: "synciki",
    storageBucket: "synciki.firebasestorage.app",
    messagingSenderId: "180478332313",
    appId: "1:180478332313:web:08015f238e6903521bd708"
};

// Initialize Firebase
firebase.initializeApp(firebaseConfig);

// Get messaging instance
const messaging = firebase.messaging();

// Handle background messages
messaging.onBackgroundMessage((payload) => {
    console.log('[firebase-messaging-sw.js] Received background message:', payload);

    const notificationTitle = payload.notification?.title || 'Synki 💕';
    const notificationOptions = {
        body: payload.notification?.body || 'Incoming call from Synki!',
        icon: '/icons/synki-icon-192.png',
        badge: '/icons/synki-badge-72.png',
        image: payload.notification?.image,
        tag: 'synki-call',
        requireInteraction: true, // Keep notification visible until user interacts
        vibrate: [200, 100, 200, 100, 200], // Vibration pattern
        data: {
            ...payload.data,
            url: self.location.origin + '/app.html'
        },
        actions: [
            {
                action: 'accept',
                title: '📞 Accept',
                icon: '/icons/accept-call.png'
            },
            {
                action: 'reject',
                title: '❌ Decline',
                icon: '/icons/reject-call.png'
            }
        ]
    };

    return self.registration.showNotification(notificationTitle, notificationOptions);
});

// Handle notification click
self.addEventListener('notificationclick', (event) => {
    console.log('[firebase-messaging-sw.js] Notification click:', event.action);

    event.notification.close();

    const action = event.action;
    const data = event.notification.data || {};

    if (action === 'accept') {
        // Open app and auto-connect
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
                // Check if app is already open
                for (const client of clientList) {
                    if (client.url.includes('/app.html') && 'focus' in client) {
                        client.focus();
                        // Send message to auto-connect
                        client.postMessage({
                            type: 'ACCEPT_CALL',
                            callId: data.call_id
                        });
                        return;
                    }
                }
                // Open new window with auto-connect parameter
                return clients.openWindow('/app.html?action=accept&call_id=' + (data.call_id || ''));
            })
        );
    } else if (action === 'reject') {
        // Optionally notify server about rejection
        if (data.call_id) {
            fetch('/api/calls/' + data.call_id + '/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(console.error);
        }
    } else {
        // Default click - open the app
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
                for (const client of clientList) {
                    if (client.url.includes('/app.html') && 'focus' in client) {
                        return client.focus();
                    }
                }
                return clients.openWindow('/app.html');
            })
        );
    }
});

// Handle push event directly (fallback)
self.addEventListener('push', (event) => {
    console.log('[firebase-messaging-sw.js] Push event:', event);
    
    if (event.data) {
        const data = event.data.json();
        console.log('[firebase-messaging-sw.js] Push data:', data);
    }
});

console.log('[firebase-messaging-sw.js] Service worker loaded');
