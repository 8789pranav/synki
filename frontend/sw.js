/**
 * Service Worker for Synki Push Notifications
 * 
 * Handles:
 * - Push notification events (incoming call, new message)
 * - Background sync for offline support
 * - Notification click handling
 */

const CACHE_NAME = 'synki-v1';

// ============================================================================
// Install Event
// ============================================================================
self.addEventListener('install', (event) => {
    console.log('Service Worker installing...');
    self.skipWaiting();
});

// ============================================================================
// Activate Event
// ============================================================================
self.addEventListener('activate', (event) => {
    console.log('Service Worker activated');
    event.waitUntil(clients.claim());
});

// ============================================================================
// Push Notification Event
// ============================================================================
self.addEventListener('push', (event) => {
    console.log('Push notification received:', event);
    
    if (!event.data) {
        console.log('No push data');
        return;
    }
    
    const data = event.data.json();
    console.log('Push data:', data);
    
    // Different notification types
    if (data.type === 'call') {
        // Incoming call notification
        event.waitUntil(showCallNotification(data));
    } else if (data.type === 'message') {
        // New message notification
        event.waitUntil(showMessageNotification(data));
    }
});

// ============================================================================
// Show Call Notification (High Priority)
// ============================================================================
async function showCallNotification(data) {
    const options = {
        body: data.message || 'Synki is calling you...',
        icon: '/icon-192.png',
        badge: '/badge-72.png',
        image: '/avatar-synki.png',
        tag: 'incoming-call',
        requireInteraction: true, // Don't auto-dismiss
        renotify: true,
        vibrate: [500, 200, 500, 200, 500], // Long vibration pattern
        actions: [
            { action: 'answer', title: '📞 Answer', icon: '/icon-answer.png' },
            { action: 'decline', title: '❌ Decline', icon: '/icon-decline.png' }
        ],
        data: {
            type: 'call',
            pending_id: data.pending_id,
            message: data.message,
            url: `/call.html?pending_id=${data.pending_id}&message=${encodeURIComponent(data.message)}`
        }
    };
    
    return self.registration.showNotification('Synki 💕 is calling', options);
}

// ============================================================================
// Show Message Notification
// ============================================================================
async function showMessageNotification(data) {
    const options = {
        body: data.message,
        icon: '/icon-192.png',
        badge: '/badge-72.png',
        tag: 'new-message',
        requireInteraction: false,
        vibrate: [200, 100, 200],
        actions: [
            { action: 'reply', title: '💬 Reply', icon: '/icon-reply.png' },
            { action: 'dismiss', title: '✕ Dismiss' }
        ],
        data: {
            type: 'message',
            pending_id: data.pending_id,
            message: data.message,
            url: `/app.html?proactive=true&pending_id=${data.pending_id}`
        }
    };
    
    return self.registration.showNotification('Synki 💕', options);
}

// ============================================================================
// Notification Click Handler
// ============================================================================
self.addEventListener('notificationclick', (event) => {
    console.log('Notification clicked:', event.action);
    
    const notification = event.notification;
    const data = notification.data;
    
    notification.close();
    
    if (data.type === 'call') {
        if (event.action === 'answer') {
            // Open call screen
            event.waitUntil(
                clients.openWindow(data.url)
            );
        } else if (event.action === 'decline') {
            // Dismiss the call
            event.waitUntil(dismissCall(data.pending_id));
        } else {
            // Default click - open call screen
            event.waitUntil(
                clients.openWindow(data.url)
            );
        }
    } else if (data.type === 'message') {
        if (event.action === 'reply') {
            // Open app to reply
            event.waitUntil(
                clients.openWindow(data.url)
            );
        } else {
            // Default click - open app
            event.waitUntil(
                clients.openWindow(data.url)
            );
        }
    }
});

// ============================================================================
// Notification Close Handler
// ============================================================================
self.addEventListener('notificationclose', (event) => {
    console.log('Notification closed');
    
    const data = event.notification.data;
    
    // If it's a call and user just closed without answering, mark as missed
    if (data.type === 'call') {
        event.waitUntil(dismissCall(data.pending_id));
    }
});

// ============================================================================
// Helper: Dismiss/Miss a call
// ============================================================================
async function dismissCall(pendingId) {
    try {
        await fetch('/api/proactive/dismiss', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pending_id: pendingId })
        });
    } catch (e) {
        console.error('Failed to dismiss call:', e);
    }
}

// ============================================================================
// Background Sync (for offline support)
// ============================================================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-messages') {
        event.waitUntil(syncMessages());
    }
});

async function syncMessages() {
    // Sync any pending messages when back online
    console.log('Syncing messages...');
}
