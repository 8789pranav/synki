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
    console.log('[FCM-SW] ===== BACKGROUND MESSAGE RECEIVED =====');
    console.log('[FCM-SW] Payload:', JSON.stringify(payload, null, 2));
    console.log('[FCM-SW] Data:', payload.data);
    console.log('[FCM-SW] Notification:', payload.notification);

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

    console.log('[FCM-SW] Showing notification:', notificationTitle);
    return self.registration.showNotification(notificationTitle, notificationOptions);
});

// Handle notification click
self.addEventListener('notificationclick', (event) => {
    console.log('[FCM-SW] ===== NOTIFICATION CLICKED =====');
    console.log('[FCM-SW] Action:', event.action);
    console.log('[FCM-SW] Notification:', event.notification);
    console.log('[FCM-SW] Data:', event.notification.data);

    event.notification.close();

    const action = event.action;
    const data = event.notification.data || {};

    if (action === 'accept') {
        console.log('[FCM-SW] User accepted call, call_id:', data.call_id);
        // Open app and auto-connect
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
                // Check if app is already open
                for (const client of clientList) {
                    if (client.url.includes('/app.html') && 'focus' in client) {
                        console.log('[FCM-SW] Focusing existing window');
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
                console.log('[FCM-SW] Opening new window for call');
                return clients.openWindow('/app.html?action=accept&call_id=' + (data.call_id || ''));
            })
        );
    } else if (action === 'reject') {
        console.log('[FCM-SW] User rejected call, call_id:', data.call_id);
        // Optionally notify server about rejection
        if (data.call_id) {
            fetch('/api/calls/' + data.call_id + '/reject', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            }).catch(err => console.error('[FCM-SW] Reject error:', err));
        }
    } else {
        console.log('[FCM-SW] Default click - opening app');
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
    console.log('[FCM-SW] ===== PUSH EVENT RECEIVED =====');
    console.log('[FCM-SW] Event:', event);
    
    if (event.data) {
        try {
            const data = event.data.json();
            console.log('[FCM-SW] Push data (JSON):', JSON.stringify(data, null, 2));
        } catch (e) {
            console.log('[FCM-SW] Push data (text):', event.data.text());
        }
    }
});

console.log('[FCM-SW] ✅ Firebase Messaging Service Worker loaded');
