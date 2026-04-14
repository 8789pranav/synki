// ===== CONFIGURATION =====
const API_BASE = 'http://localhost:8000';
const SUPABASE_URL = 'https://zdzsewasxaqatfrdvhiy.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkenNld2FzeGFxYXRmcmR2aGl5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMzY4OTAsImV4cCI6MjA5MDgxMjg5MH0.ht9J0PJKNDxdOB__SZJ7mKesexy5rBrGeCXa7g3w9kg';
const LIVEKIT_URL = 'wss://zupki-hv3uw8fv.livekit.cloud';
// NOTE: API credentials are loaded from backend .env.local - never expose in frontend
// Token is fetched from /token endpoint which has secure credentials

// Firebase Configuration - UPDATE THESE WITH YOUR FIREBASE PROJECT SETTINGS
const FIREBASE_CONFIG = {
    apiKey: "AIzaSyCkrsx1yzszd4hSSnqEHvdUmik8eae2D7E",
    authDomain: "synciki.firebaseapp.com",
    projectId: "synciki",
    storageBucket: "synciki.firebasestorage.app",
    messagingSenderId: "180478332313",
    appId: "1:180478332313:web:08015f238e6903521bd708",
    vapidKey: "BBiC1rsVVabPJhCAthXjApxMzArsmNNDvOoqHFnFLMkEged_UxSa4kCar5xMJPS7JBev1t9zeD-JmRk13OhnAbQ"
};

// Firebase variables
let firebaseApp = null;
let firebaseMessaging = null;
let pushToken = null;

// Initialize Supabase (for data only, auth via API)
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

// State
let room = null;
let currentUser = null;
let accessToken = null;
let userMemories = {};
let chatHistory = [];
let isConnected = false;  // Track connection state for P2P calls
let currentTab = 'chat';  // Current active tab

// Elements
const authContainer = document.getElementById('authContainer');
const appContainer = document.getElementById('appContainer');
const loginForm = document.getElementById('loginForm');
const signupForm = document.getElementById('signupForm');
const authError = document.getElementById('authError');
const statusEl = document.getElementById('status');
const avatarEl = document.getElementById('avatar');
const emotionBadge = document.getElementById('emotionBadge');
const transcriptEl = document.getElementById('transcript');
const memoryItems = document.getElementById('memoryItems');
const connectBtn = document.getElementById('connectBtn');
const micStatus = document.getElementById('micStatus');
const voiceStatusText = document.getElementById('voiceStatusText');

// Use voiceStatusText as avatarStatusEl fallback for new layout
const avatarStatusEl = document.getElementById('avatarStatus') || voiceStatusText;

// ===== TAB SWITCHING =====
function switchMainTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.main-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    const activeTab = document.getElementById('mainTab' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    if (activeTab) activeTab.classList.add('active');
    
    // Update tab panels
    document.querySelectorAll('.main-tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    const activePanel = document.getElementById('panel' + tabName.charAt(0).toUpperCase() + tabName.slice(1));
    if (activePanel) activePanel.classList.add('active');
    
    console.log('📑 Switched to tab:', tabName);
    
    // Load data for specific tabs
    if (tabName === 'settings') {
        loadAutoReplySettings();  // Load settings when switching to Settings tab
        loadAutoReplyMessages();  // Load caller messages
    }
}

// ===== VOICE CONNECTION TOGGLE =====
function toggleVoiceConnection() {
    if (room && room.state === 'connected') {
        // Disconnect
        disconnectFromRoom();
    } else {
        // Connect
        connectToRoom();
    }
}

// Update voice button state
function updateVoiceButton(state) {
    const voiceBtn = document.getElementById('connectBtn');
    const voiceStatus = document.getElementById('voiceStatusText');
    const disconnectBtn = document.getElementById('disconnectBtn');
    
    console.log('🔘 updateVoiceButton:', state);
    
    if (!voiceBtn) return;
    
    voiceBtn.classList.remove('active', 'connecting');
    
    switch(state) {
        case 'connecting':
            voiceBtn.classList.add('connecting');
            voiceBtn.innerHTML = '⏳';
            if (voiceStatus) voiceStatus.textContent = 'Connecting...';
            if (disconnectBtn) disconnectBtn.style.display = 'none';
            break;
        case 'connected':
            voiceBtn.classList.add('active');
            voiceBtn.innerHTML = '🎙️';
            if (voiceStatus) {
                voiceStatus.textContent = 'Connected - Talking';
                voiceStatus.classList.add('active');
            }
            // FORCE SHOW disconnect button with inline-block
            if (disconnectBtn) {
                disconnectBtn.style.display = 'inline-block';
                console.log('✅ DISCONNECT BUTTON VISIBLE');
            } else {
                console.error('❌ disconnectBtn NOT FOUND!');
            }
            break;
        case 'disconnected':
        default:
            voiceBtn.innerHTML = '🎤';
            if (voiceStatus) {
                voiceStatus.textContent = 'Click to talk with Synki';
                voiceStatus.classList.remove('active');
            }
            if (disconnectBtn) disconnectBtn.style.display = 'none';
            break;
    }
}

// ===== AUTH FUNCTIONS =====
console.log('Setting up auth handlers...');

document.getElementById('showSignup').onclick = (e) => {
    console.log('Show signup clicked');
    e.preventDefault();
    loginForm.classList.add('hidden');
    signupForm.classList.remove('hidden');
    authError.classList.remove('show');
};

document.getElementById('showLogin').onclick = (e) => {
    console.log('Show login clicked');
    e.preventDefault();
    signupForm.classList.add('hidden');
    loginForm.classList.remove('hidden');
    authError.classList.remove('show');
};

function showAuthError(msg) {
    console.log('Auth error:', msg);
    authError.textContent = msg;
    authError.classList.add('show');
}

// Sign Up
signupForm.onsubmit = async (e) => {
    console.log('Signup form submitted');
    e.preventDefault();
    const name = document.getElementById('signupName').value;
    const email = document.getElementById('signupEmail').value;
    const password = document.getElementById('signupPassword').value;

    try {
        document.getElementById('signupBtn').disabled = true;
        document.getElementById('signupBtn').textContent = 'Creating...';

        const response = await fetch(`${API_BASE}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, name })
        });
        const result = await response.json();

        if (!result.success) throw new Error(result.message);

        // Store token and show app
        accessToken = result.access_token;
        localStorage.setItem('synki_token', accessToken);
        localStorage.setItem('synki_user', JSON.stringify({
            id: result.user_id,
            email: email,
            name: result.name
        }));

        showApp({ id: result.user_id, email }, result.name);
    } catch (err) {
        showAuthError(err.message);
    } finally {
        document.getElementById('signupBtn').disabled = false;
        document.getElementById('signupBtn').textContent = '💕 Create Account';
    }
};

// Login
loginForm.onsubmit = async (e) => {
    console.log('Login form submitted');
    e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;
    console.log('Login attempt:', email);

    try {
        document.getElementById('loginBtn').disabled = true;
        document.getElementById('loginBtn').textContent = 'Logging in...';

        const response = await fetch(`${API_BASE}/auth/signin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const result = await response.json();

        if (!result.success) throw new Error(result.message);

        // Store token and show app
        accessToken = result.access_token;
        localStorage.setItem('synki_token', accessToken);
        localStorage.setItem('synki_user', JSON.stringify({
            id: result.user_id,
            email: email,
            name: result.name
        }));

        showApp({ id: result.user_id, email }, result.name);
    } catch (err) {
        showAuthError(err.message);
    } finally {
        document.getElementById('loginBtn').disabled = false;
        document.getElementById('loginBtn').textContent = '💕 Login';
    }
};

// Logout
document.getElementById('logoutBtn').onclick = async () => {
    try {
        await fetch(`${API_BASE}/auth/signout`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
    } catch (e) {}
    
    localStorage.removeItem('synki_token');
    localStorage.removeItem('synki_user');
    accessToken = null;
    currentUser = null;
    authContainer.style.display = 'block';
    appContainer.classList.remove('show');
    if (room) await room.disconnect();
};

// Audio context for unlocking audio playback
let audioContext = null;
let audioUnlocked = false;

function unlockAudio() {
    if (audioUnlocked) return;
    
    // Create audio context
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    
    // Unlock by playing silent audio
    const silentBuffer = audioContext.createBuffer(1, 1, 22050);
    const source = audioContext.createBufferSource();
    source.buffer = silentBuffer;
    source.connect(audioContext.destination);
    source.start(0);
    
    // Also pre-load ringtone
    const ringtone = document.getElementById('ringtone');
    ringtone.load();
    
    audioUnlocked = true;
    console.log('🔊 Audio unlocked');
}

// Unlock audio on any user interaction
document.addEventListener('click', unlockAudio, { once: true });
document.addEventListener('touchstart', unlockAudio, { once: true });
document.addEventListener('keydown', unlockAudio, { once: true });

// Show App
async function showApp(user, name) {
    currentUser = user;
    authContainer.style.display = 'none';
    appContainer.classList.add('show');

    document.getElementById('userName').textContent = name || 'Baby';
    document.getElementById('userEmail').textContent = user.email;
    document.getElementById('userAvatar').textContent = (name || 'U')[0].toUpperCase();

    // Load memories
    await loadMemories();
    // Load chat history
    await loadChatHistory();
    // Load auto-reply settings so they persist on reload
    await loadAutoReplySettings();
    await loadAutoReplyMessages();  // Load caller messages
    
    // Start proactive polling (checks for incoming calls/messages)
    startProactivePolling();
    
    // Start P2P call polling (checks for incoming P2P calls from friends)
    startP2PCallPolling();
    
    // Initialize push notifications
    await initializePushNotifications();
    
    // Start presence tracking (online status)
    startPresenceTracking();
}

// ===== PUSH NOTIFICATIONS (Firebase) =====
async function initializePushNotifications() {
    // Check if Firebase config is set
    if (FIREBASE_CONFIG.apiKey === "YOUR_FIREBASE_API_KEY") {
        console.log('⚠️ Firebase not configured - push notifications disabled');
        return;
    }
    
    try {
        // Initialize Firebase
        if (!firebaseApp) {
            firebaseApp = firebase.initializeApp(FIREBASE_CONFIG);
            firebaseMessaging = firebase.messaging();
            console.log('🔥 Firebase initialized');
        }
        
        // Request notification permission
        const permission = await Notification.requestPermission();
        console.log('🔔 Notification permission:', permission);
        
        if (permission === 'granted') {
            // Get FCM token
            await registerPushToken();
            
            // Listen for foreground messages
            firebaseMessaging.onMessage((payload) => {
                console.log('📩 Foreground message:', payload);
                handleForegroundMessage(payload);
            });
        } else {
            console.log('❌ Notification permission denied');
        }
    } catch (error) {
        console.error('Firebase init error:', error);
    }
}

async function registerPushToken() {
    try {
        // Register service worker
        const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
        console.log('📋 Service worker registered');
        
        // Get FCM token
        const token = await firebaseMessaging.getToken({
            vapidKey: FIREBASE_CONFIG.vapidKey, // Optional VAPID key
            serviceWorkerRegistration: registration
        });
        
        if (token) {
            pushToken = token;
            console.log('🎫 FCM Token:', token.substring(0, 20) + '...');
            
            // Register token with our backend
            const response = await fetch(`${API_BASE}/api/push/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                    token: token,
                    platform: 'web',
                    browser: navigator.userAgent.includes('Chrome') ? 'Chrome' : 
                             navigator.userAgent.includes('Firefox') ? 'Firefox' : 
                             navigator.userAgent.includes('Safari') ? 'Safari' : 'Other'
                })
            });
            
            const result = await response.json();
            if (result.success) {
                console.log('✅ Push token registered with server');
            }
        }
    } catch (error) {
        console.error('Push token registration error:', error);
    }
}

function handleForegroundMessage(payload) {
    console.log('📱 FCM foreground message:', payload);
    
    // Show notification manually when app is in foreground
    const notificationTitle = payload.notification?.title || 'Synki 💕';
    const notificationOptions = {
        body: payload.notification?.body || 'New message from Synki!',
        icon: '/icons/synki-icon-192.png',
        tag: 'synki-notification',
        requireInteraction: true,
        data: payload.data
    };
    
    // Check if this is a call notification
    if (payload.data?.type === 'incoming_call') {
        // Show incoming call UI with ringtone
        showIncomingCall({ message: payload.notification?.body || "Synki is calling..." });
        
        // Also show browser notification
        new Notification('📞 ' + notificationTitle, {
            ...notificationOptions,
            body: 'Tap to answer!',
            tag: 'synki-call'
        });
    } else {
        // Show regular notification
        new Notification(notificationTitle, notificationOptions);
    }
}

async function testPushNotification() {
    try {
        const response = await fetch(`${API_BASE}/api/push/test`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const result = await response.json();
        console.log('Test push result:', result);
        alert(result.success ? 'Test notification sent!' : 'Failed: ' + result.error);
    } catch (error) {
        console.error('Test push error:', error);
    }
}

// Load memories - via API (bypasses RLS)
async function loadMemories() {
    try {
        const response = await fetch(`${API_BASE}/api/memories/${currentUser.id}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data) {
                userMemories = data;
                displayMemories();
            }
        }
    } catch (err) {
        console.log('No memories yet');
    }
}

// Display memories
function displayMemories() {
    const items = [];
    if (userMemories.name) items.push(`Name: ${userMemories.name}`);
    if (userMemories.preferences?.favorite_topic) items.push(`Loves: ${userMemories.preferences.favorite_topic}`);
    if (userMemories.facts?.length > 0) {
        userMemories.facts.slice(-3).forEach(f => {
            // Handle fact as object or string
            const factText = typeof f === 'string' ? f : (f.fact || f.text || JSON.stringify(f));
            items.push(factText);
        });
    }

    if (items.length === 0) {
        memoryItems.innerHTML = '<div class="memory-item">Getting to know you...</div>';
    } else {
        memoryItems.innerHTML = items.map(i => `<div class="memory-item">${i}</div>`).join('');
    }
}

// Save memory
async function saveMemory(updates) {
    try {
        const newData = { ...userMemories, ...updates, updated_at: new Date().toISOString() };
        await supabaseClient
            .from('memories')
            .upsert({ user_id: currentUser.id, ...newData });
        userMemories = newData;
        displayMemories();
    } catch (err) {
        console.error('Failed to save memory:', err);
    }
}

// Load chat history
async function loadChatHistory() {
    try {
        const { data } = await supabaseClient
            .from('chat_history')
            .select('*')
            .eq('user_id', currentUser.id)
            .order('created_at', { ascending: false })
            .limit(10);

        if (data && data.length > 0) {
            chatHistory = data.reverse();
            // Show last few messages
            transcriptEl.innerHTML = '';
            chatHistory.slice(-5).forEach(msg => {
                addMessage(msg.role, msg.content, false);
            });
            addMessage('system', '💕 Previous conversation loaded. Connect to continue!');
        }
    } catch (err) {
        console.log('No chat history');
    }
}

// Save chat message
async function saveChatMessage(role, content) {
    try {
        await supabaseClient.from('chat_history').insert({
            user_id: currentUser.id,
            role: role,
            content: content,
            created_at: new Date().toISOString()
        });
    } catch (err) {
        console.error('Failed to save chat:', err);
    }
}

// ===== VOICE FUNCTIONS =====
function addMessage(type, text, save = true) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    if (type === 'user') {
        div.innerHTML = `<div class="message-label">🗣️ You</div>${text}<span class="message-time">${time}</span>`;
        if (save && currentUser) saveChatMessage('user', text);
    } else if (type === 'assistant') {
        div.innerHTML = `<div class="message-label">💕 Synki</div>${text}<span class="message-time">${time}</span>`;
        if (save && currentUser) saveChatMessage('assistant', text);
    } else {
        div.textContent = text;
    }
    
    transcriptEl.appendChild(div);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
    while (transcriptEl.children.length > 25) transcriptEl.removeChild(transcriptEl.firstChild);
}

// Detect emotion from text
function detectEmotion(text) {
    const lower = text.toLowerCase();
    if (/happy|khush|yay|great|amazing|awesome|excited/.test(lower)) return '😊 Happy';
    if (/sad|dukhi|upset|cry|miss|hurt/.test(lower)) return '😢 Sad';
    if (/tired|thak|exhausted|sleepy|neend/.test(lower)) return '😴 Tired';
    if (/stress|tension|overwhelm|pressure/.test(lower)) return '😰 Stressed';
    if (/angry|gussa|frustrated|annoyed/.test(lower)) return '😤 Frustrated';
    if (/love|pyar|miss you|i love/.test(lower)) return '💕 Loving';
    if (/bored|bore|nothing/.test(lower)) return '😐 Bored';
    return '💭 Neutral';
}

// Update emotion display
function updateEmotion(text) {
    const emotion = detectEmotion(text);
    emotionBadge.textContent = `Mood: ${emotion}`;
}

// Update persona display
const personaDescriptions = {
    'CHILL': 'Chill & Relaxed 😎',
    'PLAYFUL': 'Playful & Mischievous 😜',
    'CARING': 'Sweet & Caring 🥰',
    'CURIOUS': 'Curious & Interested 🤔'
};

function updatePersonaDisplay(persona, emoji) {
    const personaBadge = document.getElementById('personaBadge');
    if (personaBadge) {
        const desc = personaDescriptions[persona] || `${emoji} ${persona}`;
        personaBadge.textContent = desc;
        personaBadge.style.opacity = '1';
    }
}

// Generate JWT Token
async function createToken(identity, roomName) {
    const b64url = str => btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    const now = Math.floor(Date.now() / 1000);
    
    const header = { alg: 'HS256', typ: 'JWT' };
    const payload = {
        iss: API_KEY,
        sub: identity,
        iat: now,
        exp: now + 3600,
        nbf: now,
        jti: `${identity}-${now}`,
        name: identity,
        video: {
            room: roomName,
            roomJoin: true,
            roomCreate: true,
            canPublish: true,
            canSubscribe: true,
            canPublishData: true
        },
        metadata: JSON.stringify({
            user_id: currentUser?.id,
            user_name: userMemories?.name || 'Baby',
            memories: JSON.stringify(userMemories || {})
        })
    };

    const headerEnc = b64url(JSON.stringify(header));
    const payloadEnc = b64url(JSON.stringify(payload));
    const message = `${headerEnc}.${payloadEnc}`;

    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(API_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
    const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    
    return `${message}.${sigB64}`;
}

// Connect
let currentCallType = 'companion'; // 'companion' or 'topic'

// Main connect function - called by toggleVoiceConnection or button click
async function connectToRoom() {
    try {
        if (connectBtn) connectBtn.disabled = true;
        setStatus('Connecting...', '');
        updateVoiceButton('connecting');

        const roomName = `synki-${currentUser?.id || Date.now()}`;
        
        // Call API to get token AND dispatch agent
        console.log(`🔌 Requesting token from API (agent: ${currentCallType})...`);
        const tokenResponse = await fetch(`${API_BASE}/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: currentUser.id,
                room_name: roomName,
                user_name: userMemories?.name || 'Baby',
                agent_type: currentCallType
            })
        });
        
        // Reset call type after use
        currentCallType = 'companion';
        
        if (!tokenResponse.ok) {
            throw new Error(`Token request failed: ${tokenResponse.status}`);
        }
        
        const tokenData = await tokenResponse.json();
        const token = tokenData.token;
        console.log('✅ Token received, connecting to room:', roomName);

        room = new LivekitClient.Room({ adaptiveStream: true, dynacast: true });

        // Room events
        room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, pub, participant) => {
            if (track.kind === 'audio') {
                const audio = track.attach();
                document.body.appendChild(audio);
                if (avatarEl) avatarEl.classList.add('speaking');
                if (avatarEl) avatarEl.classList.remove('listening');
                if (avatarStatusEl) avatarStatusEl.textContent = 'Synki बोल रही है... 💕';
                updateVoiceButton('connected');
            }
        });

        room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            if (track.kind === 'audio') track.detach().forEach(el => el.remove());
        });

        room.on(LivekitClient.RoomEvent.TrackMuted, (pub, participant) => {
            if (!participant.isLocal) {
                if (avatarEl) avatarEl.classList.remove('speaking');
                if (avatarEl) avatarEl.classList.add('listening');
                if (avatarStatusEl) avatarStatusEl.textContent = 'सुन रही हूं जान... 🎧';
            }
        });

        room.on(LivekitClient.RoomEvent.TrackUnmuted, (pub, participant) => {
            if (!participant.isLocal && pub.kind === 'audio') {
                if (avatarEl) avatarEl.classList.add('speaking');
                if (avatarEl) avatarEl.classList.remove('listening');
                if (avatarStatusEl) avatarStatusEl.textContent = 'Synki बोल रही है... 💕';
            }
        });

        room.on(LivekitClient.RoomEvent.ParticipantConnected, (p) => {
            if (p.identity.includes('agent') || p.identity.includes('AW_')) {
                addMessage('system', '💕 Synki आ गई! बात करो baby...');
                if (avatarStatusEl) avatarStatusEl.textContent = 'Synki is here! बोलो जान...';
                setStatus('Connected 💕', 'connected');
                updateVoiceButton('connected');
            }
        });

        room.on(LivekitClient.RoomEvent.Disconnected, () => {
            handleDisconnect();
        });

        room.on(LivekitClient.RoomEvent.ActiveSpeakersChanged, (speakers) => {
            const isUserSpeaking = speakers.some(s => s.isLocal);
            if (isUserSpeaking) {
                avatarEl.classList.add('listening');
                avatarEl.classList.remove('speaking');
            }
        });

        // Data received (for transcripts and persona)
        room.on(LivekitClient.RoomEvent.DataReceived, (payload, participant) => {
            try {
                const data = JSON.parse(new TextDecoder().decode(payload));
                if (data.type === 'transcript') {
                    if (data.role === 'user') {
                        addMessage('user', data.text);
                        updateEmotion(data.text);
                    } else {
                        addMessage('assistant', data.text);
                    }
                } else if (data.type === 'persona_update') {
                    // Update UI with current persona
                    updatePersonaDisplay(data.persona, data.persona_emoji);
                    console.log('🎭 Persona:', data.persona);
                }
            } catch (e) {}
        });

        // Connect to LiveKit using URL from response or default
        const livekitUrl = tokenData.url || LIVEKIT_URL;
        console.log('🔌 Connecting to LiveKit:', livekitUrl);
        await room.connect(livekitUrl, token);
        await room.localParticipant.setMicrophoneEnabled(true);
        
        setStatus('Waiting for Synki...', 'waiting');
        if (avatarStatusEl) avatarStatusEl.textContent = 'Connecting to Synki...';
        updateVoiceButton('connecting');
        updateUI(true);
        addMessage('system', `✨ Connected! Waiting for Synki...`);

    } catch (err) {
        console.error(err);
        setStatus('Error', 'error');
        if (connectBtn) connectBtn.disabled = false;
        updateVoiceButton('disconnected');
        addMessage('system', `❌ Connection failed: ${err.message}`);
    }
}

// Button click handler - attaches after init
if (connectBtn) {
    connectBtn.onclick = () => toggleVoiceConnection();
}

// Disconnect - also can be triggered by toggleVoiceConnection
function disconnectFromRoom() {
    if (room) room.disconnect();
    handleDisconnect();
}

function handleDisconnect() {
    room = null;
    isConnected = false;
    isInP2PCall = false;
    setStatus('Disconnected', '');
    if (avatarStatusEl) avatarStatusEl.textContent = 'Click to talk again 💕';
    if (avatarEl) avatarEl.classList.remove('speaking', 'listening');
    updateVoiceButton('disconnected');
    // Reset persona badge
    const personaBadge = document.getElementById('personaBadge');
    if (personaBadge) personaBadge.textContent = '🎭 Connecting...';
    updateUI(false);
    addMessage('system', '👋 Bye bye baby! Miss you...');
    
    // Update presence to online (no longer in call)
    updateMyPresence('online', 'browsing');
    
    // Restart P2P call polling
    startP2PCallPolling();
}

function setStatus(text, className) {
    if (statusEl) {
        statusEl.textContent = text;
        statusEl.className = `status ${className}`;
    }
    // Also update statusText element if exists
    const statusText = document.getElementById('statusText');
    if (statusText) statusText.textContent = text;
}

function updateUI(connected) {
    if (connectBtn) connectBtn.disabled = connected;
    if (micStatus) {
        micStatus.classList.toggle('active', connected);
        const micSpan = micStatus.querySelector('span:last-child');
        if (micSpan) micSpan.textContent = connected ? 'Mic On 🎤' : 'Mic Off';
    }
    
    // Update presence when connecting
    if (connected) {
        updateMyPresence('in_call', 'talking_to_synki');
    }
}

// ===== INITIALIZATION =====
async function init() {
    // Check if user is already logged in (stored session)
    const storedToken = localStorage.getItem('synki_token');
    const storedUser = localStorage.getItem('synki_user');
    
    if (storedToken && storedUser) {
        try {
            const user = JSON.parse(storedUser);
            accessToken = storedToken;
            
            // Verify token is still valid
            const response = await fetch(`${API_BASE}/auth/me`, {
                headers: { 'Authorization': `Bearer ${storedToken}` }
            });
            
            if (response.ok) {
                const userData = await response.json();
                showApp({ id: userData.id, email: userData.email }, userData.name || user.name);
                
                // Start proactive polling after login
                startProactivePolling();
                
                // Start P2P call polling
                startP2PCallPolling();
            } else {
                // Token expired, clear storage
                localStorage.removeItem('synki_token');
                localStorage.removeItem('synki_user');
            }
        } catch (e) {
            console.log('Session expired');
        }
    }
    
    // Register service worker for push notifications
    registerServiceWorker();
}

// ===== PROACTIVE GF SYSTEM =====
let proactiveInterval = null;
let currentPendingContact = null;
const PROACTIVE_POLL_INTERVAL = 30000; // Check every 30 seconds

// ===== P2P CALLING SYSTEM =====
let p2pCallInterval = null;
let currentP2PCall = null;  // { id, caller_id, caller_name, room_name, created_at }
let outgoingP2PCall = null; // { room_name, target_id, target_name, status }
const P2P_POLL_INTERVAL = 2000; // Check every 2 seconds for incoming calls
let isInP2PCall = false;
let declinedCallIds = new Set(); // Track declined/answered calls to prevent re-ringing
let currentlyShowingCall = false; // Prevent showing multiple call overlays

// In-call UI state
let callDurationInterval = null;
let callStartTime = null;
let isMuted = false;
let isSpeakerOn = true;
let currentCallPeerName = 'Friend';

// Start P2P call polling
function startP2PCallPolling() {
    if (p2pCallInterval) clearInterval(p2pCallInterval);
    
    // Check immediately
    checkIncomingP2PCalls();
    
    // Then check every 2 seconds
    p2pCallInterval = setInterval(checkIncomingP2PCalls, P2P_POLL_INTERVAL);
    console.log('📞 P2P call polling started');
}

// Stop P2P call polling
function stopP2PCallPolling() {
    if (p2pCallInterval) {
        clearInterval(p2pCallInterval);
        p2pCallInterval = null;
    }
}

// Check for incoming P2P calls
async function checkIncomingP2PCalls() {
    // Don't check if already showing a call, in a call, or connected to Synki
    if (!currentUser || !accessToken || isInP2PCall || isConnected || currentlyShowingCall || currentP2PCall) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/calls/incoming`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        if (data.has_incoming_call && data.call) {
            // Skip if we already declined or answered this call
            if (declinedCallIds.has(data.call.id)) {
                console.log('📞 Skipping already handled call:', data.call.id);
                return;
            }
            
            console.log('📞 Incoming P2P call!', data.call);
            currentP2PCall = data.call;
            currentlyShowingCall = true;
            showIncomingP2PCall(data.call);
        }
    } catch (e) {
        console.log('📞 P2P call check error:', e);
    }
}

// Show incoming P2P call UI
function showIncomingP2PCall(call) {
    // Update UI elements
    document.getElementById('callerAvatar').textContent = '👤';
    document.getElementById('callerName').textContent = call.caller_name || 'Friend';
    document.getElementById('callStatusText').textContent = 'Incoming call...';
    document.getElementById('callMessage').textContent = `${call.caller_name || 'Someone'} is calling you! 📞`;
    
    // Show overlay
    document.getElementById('incomingCallOverlay').classList.remove('hidden');
    
    // Play ringtone
    const ringtone = document.getElementById('ringtone');
    ringtone.volume = 0.7;
    ringtone.currentTime = 0;
    ringtone.play().catch(e => console.log('Autoplay blocked'));
    
    // Vibrate
    if ('vibrate' in navigator) {
        const vibratePattern = () => navigator.vibrate([1000, 500, 1000, 500, 1000]);
        vibratePattern();
        window.vibrateInterval = setInterval(vibratePattern, 5000);
    }
    
    // Desktop notification
    if (Notification.permission === 'granted') {
        new Notification(`📞 ${call.caller_name || 'Someone'} is calling!`, {
            body: 'Tap to answer',
            tag: 'synki-p2p-call',
            requireInteraction: true
        });
    }
}

// Initiate a P2P direct call
async function initiateDirectCall(targetUserId, targetName) {
    if (!currentUser || !accessToken) {
        addMessage('system', '⚠️ Please log in first');
        return;
    }
    
    if (isInP2PCall || isConnected) {
        addMessage('system', '⚠️ Already in a call');
        return;
    }
    
    console.log(`📞 Initiating P2P call to ${targetName} (${targetUserId})`);
    
    // Show outgoing call overlay
    document.getElementById('outgoingCallerAvatar').textContent = targetName[0]?.toUpperCase() || '👤';
    document.getElementById('outgoingTargetName').textContent = targetName;
    document.getElementById('outgoingCallOverlay').classList.remove('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/api/call/direct/${targetUserId}`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.detail || 'Failed to initiate call');
        }
        
        console.log('📞 Call initiated:', data);
        
        outgoingP2PCall = {
            room_name: data.room_name,
            target_id: targetUserId,
            target_name: targetName,
            token: data.token,
            url: data.url,
            call_type: data.call_type,
            auto_reply: data.auto_reply
        };
        
        if (data.auto_reply) {
            // Auto-reply mode - AI secretary answers
            currentCallPeerName = `${targetName}'s AI`;
            addMessage('system', `📞 ${targetName} is unavailable. Connecting to their AI...`);
            document.getElementById('outgoingCallOverlay').classList.add('hidden');
            
            // Connect to the room with the AI
            await connectToP2PRoom(data.token, data.room_name, data.url);
        } else {
            // Direct call - wait for target to answer
            addMessage('system', `📞 Calling ${targetName}...`);
            
            // Poll for call status
            pollOutgoingCallStatus(data.room_name, data.token, data.url);
        }
        
    } catch (e) {
        console.error('📞 Call failed:', e);
        document.getElementById('outgoingCallOverlay').classList.add('hidden');
        addMessage('system', `❌ Call failed: ${e.message}`);
    }
}

// Poll for outgoing call status
async function pollOutgoingCallStatus(roomName, token, url) {
    const maxWait = 60000; // 60 seconds max wait
    const pollInterval = 2000;
    let elapsed = 0;
    
    const pollFn = async () => {
        if (!outgoingP2PCall || outgoingP2PCall.room_name !== roomName) return;
        
        elapsed += pollInterval;
        if (elapsed > maxWait) {
            // Timeout - cancel call
            cancelOutgoingCall();
            addMessage('system', `📞 ${outgoingP2PCall?.target_name || 'They'} didn't answer`);
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/calls/status/${roomName}`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            const data = await response.json();
            
            if (data.status === 'answered') {
                // They answered! Connect to room
                console.log('📞 CALLER: Call was answered!');
                currentCallPeerName = outgoingP2PCall.target_name || 'Friend';
                console.log('📞 CALLER: Setting peer name to:', currentCallPeerName);
                document.getElementById('outgoingCallOverlay').classList.add('hidden');
                addMessage('system', `📞 ${currentCallPeerName} answered! Connecting...`);
                await connectToP2PRoom(token, roomName, url);
                console.log('📞 CALLER: connectToP2PRoom completed');
                return;
            } else if (data.status === 'declined' || data.status === 'missed') {
                // Call was declined or missed
                document.getElementById('outgoingCallOverlay').classList.add('hidden');
                addMessage('system', `📞 ${outgoingP2PCall.target_name} declined the call`);
                outgoingP2PCall = null;
                return;
            }
            
            // Still ringing - continue polling
            setTimeout(pollFn, pollInterval);
        } catch (e) {
            console.error('Poll error:', e);
            setTimeout(pollFn, pollInterval);
        }
    };
    
    setTimeout(pollFn, pollInterval);
}

// Cancel outgoing call
async function cancelOutgoingCall() {
    document.getElementById('outgoingCallOverlay').classList.add('hidden');
    
    if (outgoingP2PCall) {
        try {
            await fetch(`${API_BASE}/api/calls/cancel/${outgoingP2PCall.room_name}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
        } catch (e) {
            console.log('Cancel call error:', e);
        }
        
        addMessage('system', '📞 Call cancelled');
        outgoingP2PCall = null;
    }
}

// ===== TRACK HANDLERS FOR P2P CALLS =====
function handleTrackSubscribed(track, publication, participant) {
    console.log('🔊 Track subscribed:', track.kind, 'from', participant.identity);
    if (track.kind === 'audio') {
        const audio = track.attach();
        audio.id = `audio-${participant.identity}`;
        audio.autoplay = true;
        audio.playsInline = true;
        document.body.appendChild(audio);
        
        // Ensure audio plays
        audio.play().catch(e => {
            console.warn('Audio autoplay blocked:', e);
            document.addEventListener('click', () => audio.play(), { once: true });
        });
        
        console.log('🔊 Audio attached for:', participant.identity);
        if (avatarEl) avatarEl.classList.add('speaking');
        if (avatarStatusEl) avatarStatusEl.textContent = `${participant.identity} is talking... 🎧`;
    }
}

function handleTrackUnsubscribed(track) {
    console.log('🔊 Track unsubscribed:', track.kind);
    if (track.kind === 'audio') {
        track.detach().forEach(el => el.remove());
    }
}

// Connect to a P2P room
async function connectToP2PRoom(token, roomName, url) {
    isInP2PCall = true;
    stopP2PCallPolling();
    
    try {
        // Connect using LiveKit
        room = new LivekitClient.Room();
        
        room.on(LivekitClient.RoomEvent.TrackSubscribed, handleTrackSubscribed);
        room.on(LivekitClient.RoomEvent.TrackUnsubscribed, handleTrackUnsubscribed);
        room.on(LivekitClient.RoomEvent.Disconnected, handleP2PDisconnect);
        room.on(LivekitClient.RoomEvent.ParticipantConnected, (p) => {
            console.log(`📞 ${p.identity} joined the call`);
            addMessage('system', `✅ Connected!`);
        });
        
        console.log('📞 Connecting to room:', roomName);
        await room.connect(url, token);
        console.log('📞 Connected to room successfully!');
        
        // Enable microphone
        await room.localParticipant.setMicrophoneEnabled(true);
        console.log('📞 Mic enabled');
        
        isConnected = true;
        updateUI(true);
        
        // Show in-call UI
        console.log('📞 About to show in-call UI for:', currentCallPeerName);
        try {
            showInCallUI(currentCallPeerName);
        } catch (uiError) {
            console.error('📞 ERROR showing in-call UI:', uiError);
        }
        
        console.log('📞 P2P call connected and UI shown!');
        
    } catch (e) {
        console.error('📞 Failed to connect:', e);
        addMessage('system', '❌ Failed to connect to call');
        isInP2PCall = false;
        startP2PCallPolling();
    }
}

// Handle P2P disconnect
function handleP2PDisconnect() {
    console.log('📞 handleP2PDisconnect called');
    console.log('📞 Stack trace:', new Error().stack);
    isInP2PCall = false;
    isConnected = false;
    outgoingP2PCall = null;
    currentP2PCall = null;
    hideInCallUI();
    updateUI(false);
    addMessage('system', '📞 Call ended');
    startP2PCallPolling();
}

// ===== IN-CALL UI FUNCTIONS =====
function showInCallUI(peerName) {
    console.log('📞 showInCallUI called with:', peerName);
    currentCallPeerName = peerName || 'Friend';
    document.getElementById('inCallPeerName').textContent = currentCallPeerName;
    document.getElementById('inCallAvatar').textContent = currentCallPeerName.charAt(0).toUpperCase();
    
    // Hide ALL other overlays first
    document.getElementById('outgoingCallOverlay').classList.add('hidden');
    document.getElementById('incomingCallOverlay').classList.add('hidden');
    
    // Show in-call UI
    document.getElementById('inCallOverlay').classList.remove('hidden');
    console.log('📞 In-call overlay shown!');
    
    // Start call duration timer
    callStartTime = Date.now();
    updateCallDuration();
    callDurationInterval = setInterval(updateCallDuration, 1000);
    
    // Reset button states
    isMuted = false;
    isSpeakerOn = true;
    updateMuteButton();
    updateSpeakerButton();
}

function hideInCallUI() {
    document.getElementById('inCallOverlay').classList.add('hidden');
    if (callDurationInterval) {
        clearInterval(callDurationInterval);
        callDurationInterval = null;
    }
    callStartTime = null;
}

function updateCallDuration() {
    if (!callStartTime) return;
    const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
    const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const secs = (elapsed % 60).toString().padStart(2, '0');
    document.getElementById('inCallDuration').textContent = `${mins}:${secs}`;
}

function toggleMute() {
    isMuted = !isMuted;
    if (room && room.localParticipant) {
        room.localParticipant.setMicrophoneEnabled(!isMuted);
    }
    updateMuteButton();
}

function updateMuteButton() {
    const btn = document.getElementById('muteBtn');
    const label = document.getElementById('muteBtnLabel');
    if (isMuted) {
        btn.classList.add('active');
        btn.innerHTML = '🔇<span id="muteBtnLabel">Unmute</span>';
    } else {
        btn.classList.remove('active');
        btn.innerHTML = '🎤<span id="muteBtnLabel">Mute</span>';
    }
}

function toggleSpeaker() {
    isSpeakerOn = !isSpeakerOn;
    // Control all remote audio elements
    document.querySelectorAll('audio').forEach(audio => {
        if (audio.id !== 'ringtone') {
            audio.volume = isSpeakerOn ? 1.0 : 0.3;
        }
    });
    updateSpeakerButton();
}

function updateSpeakerButton() {
    const btn = document.getElementById('speakerBtn');
    if (isSpeakerOn) {
        btn.classList.add('active');
        btn.innerHTML = '🔊<span id="speakerBtnLabel">Speaker</span>';
    } else {
        btn.classList.remove('active');
        btn.innerHTML = '🔈<span id="speakerBtnLabel">Earpiece</span>';
    }
}

async function hangupCall() {
    console.log('📞 Hanging up call...');
    hideInCallUI();
    
    if (room) {
        try {
            await room.disconnect();
        } catch (e) {
            console.error('Disconnect error:', e);
        }
    }
    
    handleP2PDisconnect();
}

// Handle incoming call actions (unified for both Synki and P2P)
function handleAcceptCall() {
    if (currentP2PCall) {
        acceptP2PCall();
    } else if (currentPendingContact) {
        acceptProactiveCall();
    }
}

function handleDeclineCall() {
    if (currentP2PCall) {
        declineP2PCall();
    } else if (currentPendingContact) {
        declineProactiveCall();
    }
}

// Accept P2P call
async function acceptP2PCall() {
    // Stop ringtone and vibration
    document.getElementById('ringtone').pause();
    document.getElementById('ringtone').currentTime = 0;
    if (window.vibrateInterval) clearInterval(window.vibrateInterval);
    navigator.vibrate && navigator.vibrate(0);
    
    // Hide overlay
    document.getElementById('incomingCallOverlay').classList.add('hidden');
    currentlyShowingCall = false;
    
    if (!currentP2PCall) {
        console.log('❌ No currentP2PCall when accepting');
        return;
    }
    
    // Mark this call as handled so we don't show it again
    declinedCallIds.add(currentP2PCall.id);
    
    const callId = currentP2PCall.id;
    const callerName = currentP2PCall.caller_name;
    
    try {
        console.log('📞 Accepting call:', callId);
        const response = await fetch(`${API_BASE}/api/calls/accept/${callId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        console.log('📞 Accept response:', data);
        
        if (data.success) {
            console.log('📞 CALLEE: Call accepted successfully!');
            currentCallPeerName = data.caller_name || callerName || 'Friend';
            console.log('📞 CALLEE: Setting peer name to:', currentCallPeerName);
            addMessage('system', `📞 Connected with ${currentCallPeerName}!`);
            isInP2PCall = true;
            await connectToP2PRoom(data.token, data.room_name, data.url);
            console.log('📞 CALLEE: connectToP2PRoom completed');
        } else {
            addMessage('system', '❌ Failed to accept call: ' + (data.detail || 'Unknown error'));
        }
    } catch (e) {
        console.error('Accept call error:', e);
        addMessage('system', '❌ Failed to accept call');
    }
    
    currentP2PCall = null;
}

// Decline P2P call
async function declineP2PCall() {
    // Stop ringtone and vibration
    document.getElementById('ringtone').pause();
    document.getElementById('ringtone').currentTime = 0;
    if (window.vibrateInterval) clearInterval(window.vibrateInterval);
    navigator.vibrate && navigator.vibrate(0);
    
    // Hide overlay
    document.getElementById('incomingCallOverlay').classList.add('hidden');
    currentlyShowingCall = false;
    
    if (currentP2PCall) {
        // Mark this call as declined so we don't show it again
        declinedCallIds.add(currentP2PCall.id);
        console.log('📞 Declining call:', currentP2PCall.id);
        
        try {
            await fetch(`${API_BASE}/api/calls/decline/${currentP2PCall.id}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
        } catch (e) {
            console.log('Decline call error:', e);
        }
        
        addMessage('system', `📞 Declined call from ${currentP2PCall.caller_name || 'Friend'}`);
    }
    
    currentP2PCall = null;
    
    // Clear old declined calls after 5 minutes to prevent memory buildup
    setTimeout(() => {
        if (declinedCallIds.size > 50) {
            declinedCallIds.clear();
        }
    }, 300000);
}

// Start P2P call polling (now starts after auth)

// Start polling for proactive contacts
function startProactivePolling() {
    if (proactiveInterval) clearInterval(proactiveInterval);
    
    // Check immediately
    checkProactiveContacts();
    
    // Then check periodically
    proactiveInterval = setInterval(checkProactiveContacts, PROACTIVE_POLL_INTERVAL);
    console.log('🔔 Proactive polling started');
}

// Stop polling
function stopProactivePolling() {
    if (proactiveInterval) {
        clearInterval(proactiveInterval);
        proactiveInterval = null;
    }
}

// Check for pending proactive contacts
async function checkProactiveContacts() {
    if (!currentUser) {
        console.log('🔔 Proactive check: No user logged in');
        return;
    }
    
    console.log(`🔔 Checking proactive contacts for user: ${currentUser.id}`);
    
    try {
        const response = await fetch(`${API_BASE}/api/proactive/pending?user_id=${currentUser.id}`);
        const data = await response.json();
        
        console.log('🔔 Proactive response:', data);
        
        if (data.pending && data.pending.length > 0) {
            const contact = data.pending[0]; // Get first pending
            console.log('🔔 Incoming contact!', contact);
            handleProactiveContact(contact);
        } else {
            console.log('🔔 No pending contacts');
        }
    } catch (e) {
        console.log('🔔 Proactive check failed:', e);
    }
    
    // Also check for connection requests (silently update badge)
    try {
        await checkConnectionRequests();
    } catch (e) {
        console.log('🔔 Connection check failed:', e);
    }
}

// Check for pending connection requests (updates badge)
async function checkConnectionRequests() {
    if (!accessToken) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/connections`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        pendingRequests = data.pending_requests || [];
        updateRequestsBadge();
    } catch (e) {
        // Silently fail
    }
}

// Handle a proactive contact
function handleProactiveContact(contact) {
    currentPendingContact = contact;
    
    if (contact.contact_type === 'call') {
        showIncomingCall(contact);
    } else {
        showMessageNotification(contact);
    }
}

// Show incoming call UI
function showIncomingCall(contact) {
    document.getElementById('callMessage').textContent = contact.message || 'Miss kar rahi thi...';
    document.getElementById('incomingCallOverlay').classList.remove('hidden');
    
    // Play ringtone (try multiple times)
    const ringtone = document.getElementById('ringtone');
    ringtone.volume = 0.7;
    ringtone.currentTime = 0;
    
    const playRingtone = () => {
        ringtone.play().then(() => {
            console.log('🔔 Ringtone playing!');
        }).catch(e => {
            console.log('⚠️ Autoplay blocked, retrying on interaction...');
            // Retry on next user interaction
            document.addEventListener('click', () => {
                ringtone.play().catch(() => {});
            }, { once: true });
        });
    };
    
    playRingtone();
    
    // Vibrate pattern (phone-like ringing)
    if ('vibrate' in navigator) {
        // Ring pattern: vibrate 1s, pause 0.5s, repeat
        const vibratePattern = () => {
            navigator.vibrate([1000, 500, 1000, 500, 1000, 500, 1000]);
        };
        vibratePattern();
        // Repeat vibration every 5 seconds
        window.vibrateInterval = setInterval(vibratePattern, 5000);
    }
    
    // Show desktop notification too (in case tab is in background)
    if (Notification.permission === 'granted') {
        new Notification('📞 Synki is calling!', {
            body: contact.message || 'Tap to answer',
            icon: '/icons/synki-icon-192.png',
            tag: 'synki-incoming-call',
            requireInteraction: true
        });
    }
}

// Accept proactive call
async function acceptProactiveCall() {
    // Stop ringtone and vibration
    document.getElementById('ringtone').pause();
    document.getElementById('ringtone').currentTime = 0;
    if (window.vibrateInterval) clearInterval(window.vibrateInterval);
    navigator.vibrate && navigator.vibrate(0);
    
    // Hide overlay
    document.getElementById('incomingCallOverlay').classList.add('hidden');
    
    // Check if this is a topic call (scheduled by someone with specific questions)
    let isTopicCall = false;
    let topicContext = null;
    
    // Answer the call on backend
    if (currentPendingContact) {
        try {
            const response = await fetch(`${API_BASE}/api/proactive/answer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pending_id: currentPendingContact.id, user_id: currentUser.id })
            });
            const data = await response.json();
            
            console.log('📞 Proactive answer response:', data);
            
            // Store greeting for agent to use
            if (data.greeting) {
                sessionStorage.setItem('proactive_greeting', data.greeting);
            }
            
            // Check if context has topic prompts (scheduled topic call)
            topicContext = data.context || {};
            console.log('📋 Topic context:', topicContext);
            console.log('📋 Topic prompts:', topicContext.topic_prompts);
            
            if (topicContext.topic_prompts && topicContext.topic_prompts.length > 0) {
                isTopicCall = true;
                console.log('✅ TOPIC CALL DETECTED! Prompts:', topicContext.topic_prompts);
            } else {
                console.log('❌ No topic prompts - using girlfriend mode');
            }
        } catch (e) {
            console.log('Failed to answer:', e);
        }
    }
    
    // Set call type before connecting
    currentCallType = isTopicCall ? 'topic' : 'companion';
    console.log(`📞 Connecting with agent type: ${currentCallType}`);
    
    // Auto-connect to voice agent
    addMessage('system', isTopicCall ? `📞 Topic call: ${topicContext.topic_title || 'Check-in'} - Connecting...` : '📞 Synki called you! Connecting...');
    connectBtn.click();
    
    currentPendingContact = null;
}

// Decline proactive call
async function declineProactiveCall() {
    // Stop ringtone and vibration
    document.getElementById('ringtone').pause();
    document.getElementById('ringtone').currentTime = 0;
    if (window.vibrateInterval) clearInterval(window.vibrateInterval);
    navigator.vibrate && navigator.vibrate(0);
    
    // Hide overlay
    document.getElementById('incomingCallOverlay').classList.add('hidden');
    
    // Mark as missed
    if (currentPendingContact) {
        try {
            await fetch(`${API_BASE}/api/proactive/dismiss`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pending_id: currentPendingContact.id, user_id: currentUser.id })
            });
        } catch (e) {}
    }
    
    addMessage('system', '📞 Missed call from Synki 💔');
    currentPendingContact = null;
}

// Show message notification
function showMessageNotification(contact) {
    // Create notification badge
    const notif = document.createElement('div');
    notif.className = 'notification-badge';
    notif.innerHTML = `
        <button class="notif-close" onclick="this.parentElement.remove()">×</button>
        <div class="notif-title">💕 Synki</div>
        <div class="notif-message">${contact.message}</div>
    `;
    notif.onclick = (e) => {
        if (e.target.classList.contains('notif-close')) return;
        notif.remove();
        replyToMessage(contact);
    };
    
    document.body.appendChild(notif);
    
    // Auto-remove after 10 seconds
    setTimeout(() => notif.remove(), 10000);
    
    // Mark as read
    fetch(`${API_BASE}/api/proactive/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pending_id: contact.id, user_id: currentUser.id })
    }).catch(() => {});
}

// Reply to message (connect and talk)
function replyToMessage(contact) {
    addMessage('assistant', contact.message);
    addMessage('system', '💬 Click Connect to reply!');
}

// ===== PROMPT VIEWER =====
function togglePromptViewer() {
    const viewer = document.getElementById('promptViewer');
    const toggle = document.getElementById('promptToggle');
    if (viewer.style.display === 'none') {
        viewer.style.display = 'block';
        toggle.textContent = '▼';
    } else {
        viewer.style.display = 'none';
        toggle.textContent = '▶';
    }
}

async function loadAgentPrompt() {
    if (!currentUser) {
        document.getElementById('promptContent').textContent = 'Please log in first.';
        return;
    }
    
    document.getElementById('promptContent').textContent = 'Loading...';
    
    try {
        const response = await fetch(`${API_BASE}/api/agent/prompt?user_id=${currentUser.id}`);
        const data = await response.json();
        
        let content = `╔═══════════════════════════════════════════════════╗\n`;
        content += `║        SYNKI AGENT PROMPT VIEWER                  ║\n`;
        content += `╚═══════════════════════════════════════════════════╝\n\n`;
        
        // Profile section
        content += `📋 PROFILE SETTINGS:\n`;
        content += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
        content += `   Mode: ${data.profile.mode}\n`;
        content += `   Language: ${data.profile.language_style}\n`;
        content += `   Tone: ${data.profile.tone}\n`;
        content += `   Question Limit: ${data.profile.question_limit}\n\n`;
        
        // Context Data section
        if (data.context_data) {
            content += `🧠 CONTEXT BUILDER DATA:\n`;
            content += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
            content += `   User: ${data.context_data.user_name || 'Unknown'}\n`;
            content += `   Mood: ${data.context_data.current_mood}\n`;
            content += `   Stress: ${data.context_data.stress_level}\n`;
            content += `   Time: ${data.context_data.time_of_day}\n`;
            content += `   Hint: ${data.context_data.time_based_hint || 'None'}\n`;
            content += `   Summaries: ${data.context_data.recent_summaries_count} loaded\n`;
            
            if (data.context_data.questions_already_asked?.length > 0) {
                content += `   Questions Asked: ${data.context_data.questions_already_asked.join(', ')}\n`;
            }
            if (data.context_data.conversation_flow?.length > 0) {
                content += `   Flow: ${data.context_data.conversation_flow.join(' → ')}\n`;
            }
            if (Object.keys(data.context_data.likes || {}).length > 0) {
                content += `   Likes: ${JSON.stringify(data.context_data.likes)}\n`;
            }
            if (Object.keys(data.context_data.dislikes || {}).length > 0) {
                content += `   Dislikes: ${JSON.stringify(data.context_data.dislikes)}\n`;
            }
            if (data.context_data.behavior_hint) {
                content += `   Behavior: ${data.context_data.behavior_hint}\n`;
            }
            if (data.context_data.contextual_suggestion) {
                content += `   Suggestion: ${data.context_data.contextual_suggestion}\n`;
            }
            content += '\n';
        }
        
        // Memory Facts
        if (data.memory_facts && data.memory_facts.length > 0) {
            content += `📝 MEMORY FACTS:\n`;
            content += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
            data.memory_facts.forEach((fact, i) => {
                content += `   ${i+1}. ${fact}\n`;
            });
            content += '\n';
        }
        
        // System Prompt
        content += `🤖 SYSTEM PROMPT (Base):\n`;
        content += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
        content += data.system_prompt + '\n\n';
        
        // Context Injection (the SMART part!)
        content += `✨ CONTEXT INJECTION (Smart Context Builder):\n`;
        content += `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
        if (data.context_injection) {
            content += data.context_injection + '\n';
        } else {
            content += '   [No context injection available]\n';
        }
        
        document.getElementById('promptContent').textContent = content;
    } catch (e) {
        document.getElementById('promptContent').textContent = `Error loading prompt: ${e.message}`;
    }
}

// Register service worker
async function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        try {
            const registration = await navigator.serviceWorker.register('/sw.js');
            console.log('Service Worker registered:', registration.scope);
            
            // Request notification permission
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission();
            }
        } catch (e) {
            console.log('Service Worker registration failed:', e);
        }
    }
}

// ===== SCHEDULE CALL FUNCTIONS =====
let scheduledCallTime = null;
let scheduledCallId = null;
let scheduledCallInterval = null;
let scheduledCallTimeout = null;

// Family and topics data
let familyMembers = [];
let synkiConnections = [];  // Synki users (have their own app)
let callTopics = [];

async function openScheduleModal() {
    document.getElementById('scheduleModal').classList.remove('hidden');
    document.querySelectorAll('.quick-btn').forEach(b => b.classList.remove('selected'));
    document.getElementById('customMinutes').value = 10;
    
    // Load family members, Synki connections, and topics
    await loadFamilyMembers();
    await loadSynkiConnections();
    await loadCallTopics();
}

async function loadFamilyMembers() {
    try {
        const response = await fetch(`${API_BASE}/api/linked-users/${currentUser.id}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        familyMembers = data.users || [];
        
        updateRecipientDropdown();
    } catch (e) {
        console.error('Failed to load family:', e);
    }
}

async function loadSynkiConnections() {
    try {
        const response = await fetch(`${API_BASE}/api/connections?status=accepted`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        synkiConnections = data.connections || [];
        
        updateRecipientDropdown();
    } catch (e) {
        console.error('Failed to load connections:', e);
    }
}

function updateRecipientDropdown() {
    const select = document.getElementById('callRecipient');
    select.innerHTML = '<option value="self">🙋 Me</option>';
    
    // Add Synki connections first (they have the app)
    if (synkiConnections.length > 0) {
        select.innerHTML += '<optgroup label="📱 Synki Friends (have the app)">';
        synkiConnections.forEach(conn => {
            select.innerHTML += `<option value="connection:${conn.connection_id}">💜 ${conn.other_user_name || 'Friend'}</option>`;
        });
        select.innerHTML += '</optgroup>';
    }
    
    // Add linked family members (don't have the app)
    if (familyMembers.length > 0) {
        select.innerHTML += '<optgroup label="👨‍👩‍👧 Family (no app)">';
        familyMembers.forEach(member => {
            const emoji = member.avatar_emoji || '👤';
            select.innerHTML += `<option value="linked:${member.id}">${emoji} ${member.name}</option>`;
        });
        select.innerHTML += '</optgroup>';
    }
}

async function loadCallTopics() {
    try {
        const response = await fetch(`${API_BASE}/api/call-topics/${currentUser.id}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        callTopics = data.topics || [];
        
        // Update dropdown
        const select = document.getElementById('callTopic');
        select.innerHTML = '<option value="">💕 General Check-in</option>';
        
        callTopics.forEach(topic => {
            const emoji = topic.emoji || '💬';
            select.innerHTML += `<option value="${topic.id}">${emoji} ${topic.title}</option>`;
        });
    } catch (e) {
        console.error('Failed to load topics:', e);
    }
}

function toggleTopicSection() {
    // Topic section is now always visible
    const recipient = document.getElementById('callRecipient').value;
    const topicSection = document.getElementById('topicSection');
    // Always show - topics work for all call types now
    topicSection.style.display = 'block';
}

function closeScheduleModal() {
    document.getElementById('scheduleModal').classList.add('hidden');
}

function selectQuickTime(btn, minutes) {
    document.querySelectorAll('.quick-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    document.getElementById('customMinutes').value = minutes;
}

async function confirmScheduleCall() {
    const minutes = parseInt(document.getElementById('customMinutes').value) || 10;
    const recipient = document.getElementById('callRecipient').value;
    const topicId = document.getElementById('callTopic').value;
    const topic = callTopics.find(t => t.id === topicId);
    
    if (minutes < 1 || minutes > 180) {
        alert('Please enter 1-180 minutes');
        return;
    }

    const scheduledAt = new Date(Date.now() + (minutes * 60 * 1000));
    
    // Parse recipient type
    const [recipientType, recipientId] = recipient.includes(':') ? recipient.split(':') : ['self', null];
    
    if (recipientType === 'self' || recipient === 'self') {
        // Regular self call (with optional topic)
        scheduledCallTime = scheduledAt.getTime();
        
        // Check if topic selected
        const hasTopicPrompts = topic && topic.prompts && topic.prompts.length > 0;
        const callTypeLabel = hasTopicPrompts ? `Topic call: ${topic.title}` : 'Scheduled call';
        
        try {
            const response = await fetch(`${API_BASE}/api/schedule/${currentUser.id}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                    scheduled_at: scheduledAt.toISOString(),
                    call_type: 'scheduled',
                    message: hasTopicPrompts ? `${topic.emoji || '📝'} ${topic.title}` : `Scheduled call - ${minutes} min timer! 💕`,
                    topic_id: topicId || null,
                    topic_title: topic?.title || null,
                    topic_prompts: topic?.prompts || []
                })
            });

            const data = await response.json();
            
            if (data.success) {
                scheduledCallId = data.call_id;
                localStorage.setItem('scheduledCallTime', scheduledCallTime.toString());
                localStorage.setItem('scheduledCallId', scheduledCallId);
                
                closeScheduleModal();
                
                // Show indicator
                document.getElementById('scheduledIndicator').style.display = 'flex';
                document.getElementById('scheduleCallBtn').style.display = 'none';
                
                // Start countdown
                updateScheduleCountdown();
                scheduledCallInterval = setInterval(updateScheduleCountdown, 1000);
                
                // Set backup timeout
                scheduledCallTimeout = setTimeout(triggerScheduledCall, (minutes * 60 * 1000) + 30000);
                
                // Show success message with topic info
                const topicMsg = hasTopicPrompts ? ` about "${topic.title}"` : '';
                addMessage('system', `⏰ Synki will call you${topicMsg} in ${minutes} minute${minutes > 1 ? 's' : ''}! 💕`);
            } else {
                alert('Failed to schedule call');
            }
        } catch (error) {
            console.error('Schedule error:', error);
            alert('Failed to schedule call');
        }
    } else if (recipientType === 'connection') {
        // Call to Synki connection (they have the app)
        try {
            const conn = synkiConnections.find(c => c.connection_id === recipientId);
            const topicName = topic?.title || 'check-in';
            
            const response = await fetch(`${API_BASE}/api/connections/${recipientId}/schedule-call`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                    scheduled_at: scheduledAt.toISOString(),
                    message: topic ? `${topic.emoji} ${topic.title}` : 'Synki wants to chat! 💕',
                    topic_id: topicId || null,
                    topic_prompts: topic?.prompts || []
                })
            });

            const data = await response.json();
            
            if (data.success) {
                closeScheduleModal();
                const friendName = conn?.other_user_name || 'your friend';
                addMessage('system', `💜 Synki will call ${friendName} in ${minutes} minute${minutes > 1 ? 's' : ''} to talk about ${topicName}! 📱`);
                showToast(`Call scheduled for ${friendName}!`, 'success');
            } else {
                alert(data.message || 'Failed to schedule call');
            }
        } catch (error) {
            console.error('Connection call error:', error);
            alert('Failed to schedule call');
        }
    } else if (recipientType === 'linked') {
        // Delegated call to linked family (no app)
        try {
            const familyMember = familyMembers.find(m => m.id === recipientId);
            
            const response = await fetch(`${API_BASE}/api/delegated-calls/${currentUser.id}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                    linked_user_id: recipientId,
                    scheduled_at: scheduledAt.toISOString(),
                    topic_id: topicId || null,
                    custom_message: topic ? `${topic.emoji} ${topic.title}` : 'Check-in call from Synki 💕'
                })
            });

            const data = await response.json();
            
            if (data.success) {
                closeScheduleModal();
                
                const memberName = familyMember?.name || 'family member';
                const topicName = topic?.title || 'check-in';
                addMessage('system', `👨‍👩‍👧 Synki will call ${memberName} in ${minutes} minute${minutes > 1 ? 's' : ''} for ${topicName}! 💕`);
            } else {
                alert('Failed to schedule family call');
            }
        } catch (error) {
            console.error('Delegated call error:', error);
            alert('Failed to schedule family call');
        }
    }
}

function updateScheduleCountdown() {
    if (!scheduledCallTime) return;
    
    const remaining = scheduledCallTime - Date.now();
    
    if (remaining <= 0) {
        document.getElementById('scheduledCountdown').textContent = '00:00';
        return;
    }
    
    const mins = Math.floor(remaining / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    document.getElementById('scheduledCountdown').textContent = 
        `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

async function cancelScheduledCall() {
    if (scheduledCallTimeout) clearTimeout(scheduledCallTimeout);
    if (scheduledCallInterval) clearInterval(scheduledCallInterval);
    
    // Cancel on server
    if (scheduledCallId && currentUser) {
        try {
            await fetch(`${API_BASE}/api/schedule/${currentUser.id}/${scheduledCallId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
        } catch (e) { console.error('Cancel error:', e); }
    }
    
    scheduledCallTime = null;
    scheduledCallId = null;
    localStorage.removeItem('scheduledCallTime');
    localStorage.removeItem('scheduledCallId');
    
    document.getElementById('scheduledIndicator').style.display = 'none';
    document.getElementById('scheduleCallBtn').style.display = 'inline-flex';
    
    addMessage('system', '❌ Scheduled call cancelled');
}

function triggerScheduledCall() {
    if (scheduledCallInterval) clearInterval(scheduledCallInterval);
    
    scheduledCallTime = null;
    scheduledCallId = null;
    localStorage.removeItem('scheduledCallTime');
    localStorage.removeItem('scheduledCallId');
    
    document.getElementById('scheduledIndicator').style.display = 'none';
    document.getElementById('scheduleCallBtn').style.display = 'inline-flex';
    
    // Show browser notification if permitted
    if (Notification.permission === 'granted') {
        new Notification('Synki is calling! 💕', {
            body: 'Your scheduled call is ready!',
            icon: '/frontend/favicon.ico'
        });
    }
    
    console.log('📞 Scheduled call triggered!');
}

// ===== FAMILY MEMBERS MANAGEMENT =====

function openFamilyModal() {
    closeScheduleModal();
    document.getElementById('familyModal').classList.remove('hidden');
    document.getElementById('addFamilyForm').style.display = 'none';
    renderFamilyList();
}

function closeFamilyModal() {
    document.getElementById('familyModal').classList.add('hidden');
}

function renderFamilyList() {
    const list = document.getElementById('familyList');
    
    if (familyMembers.length === 0) {
        list.innerHTML = `
            <div style="text-align: center; padding: 20px; color: var(--text-secondary);">
                <span style="font-size: 2rem;">👨‍👩‍👧</span>
                <p>No family members yet</p>
                <p style="font-size: 0.85rem;">Add someone for Synki to check on!</p>
            </div>
        `;
        return;
    }
    
    list.innerHTML = familyMembers.map(member => `
        <div style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--surface); border-radius: 12px; margin-bottom: 10px;">
            <span style="font-size: 1.8rem;">${member.avatar_emoji || '👤'}</span>
            <div style="flex: 1;">
                <div style="font-weight: 600; color: var(--text-primary);">${member.name}</div>
                <div style="font-size: 0.8rem; color: var(--text-secondary);">${member.relationship} • ${member.speaking_pace || 'normal'} pace</div>
                ${member.phone ? `<div style="font-size: 0.75rem; color: var(--text-muted);">📞 ${member.phone}</div>` : ''}
            </div>
            <button onclick="deleteFamilyMember('${member.id}')" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 5px;">🗑️</button>
        </div>
    `).join('');
}

function showAddFamilyForm() {
    document.getElementById('addFamilyForm').style.display = 'block';
    document.getElementById('familyName').value = '';
    document.getElementById('familyPhone').value = '';
    document.getElementById('familyNotes').value = '';
}

async function saveFamilyMember() {
    const name = document.getElementById('familyName').value.trim();
    const relationship = document.getElementById('familyRelation').value;
    const phone = document.getElementById('familyPhone').value.trim();
    const speakingPace = document.getElementById('familySpeakingPace').value;
    const notes = document.getElementById('familyNotes').value.trim();
    
    if (!name) {
        alert('Please enter a name');
        return;
    }
    
    // Get emoji based on relationship
    const emojiMap = {
        'mom': '👩',
        'dad': '👨',
        'grandma': '👵',
        'grandpa': '👴',
        'friend': '🧑',
        'other': '👤'
    };
    
    try {
        const response = await fetch(`${API_BASE}/api/linked-users/${currentUser.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                name,
                relationship,
                phone: phone || null,
                avatar_emoji: emojiMap[relationship] || '👤',
                speaking_pace: speakingPace,
                notes: notes || null
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Reload family members
            await loadFamilyMembers();
            renderFamilyList();
            document.getElementById('addFamilyForm').style.display = 'none';
            addMessage('system', `👨‍👩‍👧 Added ${name} to your family! Synki can now call them.`);
        } else {
            alert('Failed to add family member');
        }
    } catch (e) {
        console.error('Failed to save family member:', e);
        alert('Failed to add family member');
    }
}

async function deleteFamilyMember(id) {
    if (!confirm('Remove this family member?')) return;
    
    try {
        await fetch(`${API_BASE}/api/linked-users/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        
        // Reload
        await loadFamilyMembers();
        renderFamilyList();
    } catch (e) {
        console.error('Failed to delete:', e);
    }
}

// ===== SYNKI CONNECTIONS (Social) =====

let mySynkiCode = null;
let myConnections = [];
let pendingRequests = [];
let sentRequests = [];
let connectionsPresence = {};  // Map of user_id -> presence data
let currentConnectionTab = 'my-code';
let presenceInterval = null;

async function openConnectionsModal() {
    document.getElementById('connectionsModal').classList.remove('hidden');
    // Reset to first tab
    switchConnectionTab('my-code');
    
    // Load data with loading states
    const codeEl = document.getElementById('mySynkiCode');
    codeEl.classList.add('loading');
    codeEl.textContent = '------';
    
    await Promise.all([
        loadMySynkiCode(),
        loadConnections(),
        loadConnectionsPresence()
    ]);
}

function closeConnectionsModal() {
    document.getElementById('connectionsModal').classList.add('hidden');
    document.getElementById('searchResult').style.display = 'none';
    document.getElementById('connectCode').value = '';
    document.getElementById('searchPlaceholder').style.display = 'block';
}

function switchConnectionTab(tabId) {
    currentConnectionTab = tabId;
    
    // Update tab buttons
    document.querySelectorAll('.modal-tab').forEach(tab => tab.classList.remove('active'));
    document.getElementById(`tab${tabId.charAt(0).toUpperCase() + tabId.slice(1).replace(/-([a-z])/g, g => g[1].toUpperCase())}`).classList.add('active');
    
    // Update panels
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
    const panelId = `panel${tabId.charAt(0).toUpperCase() + tabId.slice(1).replace(/-([a-z])/g, g => g[1].toUpperCase())}`;
    document.getElementById(panelId).classList.add('active');
    
    // Load data for specific tabs
    if (tabId === 'scheduled') {
        loadScheduledCalls();
    }
}

async function loadScheduledCalls() {
    const container = document.getElementById('scheduledCallsList');
    container.innerHTML = '<div class="loading-state">Loading...</div>';
    
    try {
        const response = await fetch(`${API_BASE}/api/schedule/my-scheduled`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        const forMe = data.for_me || [];
        const byMe = data.by_me || [];
        const total = forMe.length + byMe.length;
        
        // Update badge
        const badge = document.getElementById('scheduledBadge');
        if (total > 0) {
            badge.textContent = total;
            badge.style.display = 'inline-flex';
        } else {
            badge.style.display = 'none';
        }
        
        if (total === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⏰</div>
                    <div class="empty-state-title">No scheduled calls</div>
                    <div class="empty-state-text">Schedule calls from the main screen or from a friend's profile</div>
                </div>
            `;
            return;
        }
        
        let html = '';
        
        // Calls scheduled FOR ME (someone else scheduled)
        if (forMe.length > 0) {
            html += `<div class="scheduled-section">
                <div class="scheduled-section-title">📥 Calls Coming to Me</div>`;
            
            forMe.forEach(call => {
                const time = new Date(call.scheduled_at);
                const timeStr = time.toLocaleString('en-IN', { 
                    weekday: 'short',
                    hour: '2-digit', 
                    minute: '2-digit',
                    day: 'numeric',
                    month: 'short'
                });
                const metadata = call.metadata || {};
                const scheduledBy = metadata.scheduled_by_name || 'Someone';
                const topicTitle = metadata.topic_title || 'General check-in';
                const topicEmoji = metadata.topic_emoji || '💬';
                
                html += `
                    <div class="scheduled-call-card">
                        <div class="scheduled-call-info">
                            <div class="scheduled-call-topic">${topicEmoji} ${topicTitle}</div>
                            <div class="scheduled-call-by">Scheduled by ${scheduledBy}</div>
                            <div class="scheduled-call-time">⏰ ${timeStr}</div>
                        </div>
                        <button class="scheduled-call-cancel" onclick="cancelScheduledCall('${call.id}')">✕</button>
                    </div>
                `;
            });
            html += '</div>';
        }
        
        // Calls scheduled BY ME (for others)
        if (byMe.length > 0) {
            html += `<div class="scheduled-section" style="margin-top: 20px;">
                <div class="scheduled-section-title">📤 Calls I've Scheduled</div>`;
            
            byMe.forEach(call => {
                const time = new Date(call.scheduled_at);
                const timeStr = time.toLocaleString('en-IN', { 
                    weekday: 'short',
                    hour: '2-digit', 
                    minute: '2-digit',
                    day: 'numeric',
                    month: 'short'
                });
                const metadata = call.metadata || {};
                const topicTitle = metadata.topic_title || 'General check-in';
                const topicEmoji = metadata.topic_emoji || '💬';
                const targetName = call.target_name || 'Friend';
                
                html += `
                    <div class="scheduled-call-card scheduled-by-me">
                        <div class="scheduled-call-info">
                            <div class="scheduled-call-topic">${topicEmoji} ${topicTitle}</div>
                            <div class="scheduled-call-by">For ${targetName}</div>
                            <div class="scheduled-call-time">⏰ ${timeStr}</div>
                        </div>
                        <button class="scheduled-call-cancel" onclick="cancelScheduledCallForOther('${call.id}')">✕</button>
                    </div>
                `;
            });
            html += '</div>';
        }
        
        container.innerHTML = html;
        
    } catch (e) {
        console.error('Failed to load scheduled calls:', e);
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">❌</div>
                <div class="empty-state-title">Failed to load</div>
                <div class="empty-state-text">Please try again</div>
            </div>
        `;
    }
}

async function cancelScheduledCallForOther(callId) {
    if (!confirm('Cancel this scheduled call?')) return;
    
    try {
        // We need a new API endpoint for this
        const response = await fetch(`${API_BASE}/api/schedule/cancel/${callId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        
        if (response.ok) {
            loadScheduledCalls();
        } else {
            alert('Failed to cancel call');
        }
    } catch (e) {
        console.error('Failed to cancel:', e);
        alert('Failed to cancel call');
    }
}

async function loadMySynkiCode() {
    const codeEl = document.getElementById('mySynkiCode');
    try {
        const response = await fetch(`${API_BASE}/api/connections/my-code`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        mySynkiCode = data.code;
        codeEl.textContent = mySynkiCode || '------';
        codeEl.classList.remove('loading');
    } catch (e) {
        console.error('Failed to load code:', e);
        codeEl.textContent = 'ERROR';
        codeEl.classList.remove('loading');
    }
}

function copyMyCode() {
    const btn = document.getElementById('copyCodeBtn');
    if (mySynkiCode) {
        navigator.clipboard.writeText(mySynkiCode).then(() => {
            btn.innerHTML = '<span>✓</span> Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = '<span>📋</span> Copy Code';
                btn.classList.remove('copied');
            }, 2000);
        });
    }
}

async function loadConnections() {
    try {
        const response = await fetch(`${API_BASE}/api/connections`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        myConnections = data.connections || [];
        pendingRequests = data.pending_requests || [];
        sentRequests = data.sent_requests || [];
        
        renderConnections();
        renderPendingRequests();
        updateRequestsBadge();
    } catch (e) {
        console.error('Failed to load connections:', e);
    }
}

function updateRequestsBadge() {
    const modalBadge = document.getElementById('requestsBadge');
    const headerBadge = document.getElementById('headerRequestsBadge');
    const count = pendingRequests.length;
    
    // Update modal badge
    if (count > 0) {
        modalBadge.textContent = count;
        modalBadge.style.display = 'flex';
    } else {
        modalBadge.style.display = 'none';
    }
    
    // Update header badge
    if (headerBadge) {
        if (count > 0) {
            headerBadge.textContent = count;
            headerBadge.style.display = 'flex';
        } else {
            headerBadge.style.display = 'none';
        }
    }
}

function renderConnections() {
    const list = document.getElementById('connectionsList');
    
    if (myConnections.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">💕</div>
                <div class="empty-state-title">No connections yet</div>
                <div class="empty-state-text">Share your Synki code or search for friends to connect!</div>
            </div>
        `;
        return;
    }
    
    const getRelationEmoji = (rel) => {
        const emojis = { family: '👨‍👩‍👧', friend: '🧑', caregiver: '💝', parent: '👴', child: '👶' };
        return emojis[rel] || '👤';
    };
    
    const getStatusText = (status) => {
        const texts = {
            'online': 'Online',
            'in_call': 'In Call 📞',
            'away': 'Away',
            'busy': 'Busy'
        };
        return texts[status] || '';
    };
    
    list.innerHTML = `
        <div class="section-header">
            <span class="section-title">💕 Your Connections</span>
            <span class="section-count">${myConnections.length}</span>
        </div>
        ${myConnections.map(conn => {
            const presence = connectionsPresence[conn.other_user_id] || {};
            const isOnline = presence.is_online || false;
            const status = presence.status || 'offline';
            const statusText = isOnline ? getStatusText(status) : '';
            
            return `
            <div class="connection-card" data-user-id="${conn.other_user_id}">
                <div class="connection-avatar">
                    ${(conn.other_user_name || 'U')[0].toUpperCase()}
                    <span class="status-indicator ${status}"></span>
                </div>
                <div class="connection-info">
                    <div class="connection-name">
                        ${conn.nickname || conn.other_user_name}
                        ${statusText ? `<span class="connection-status-text ${status}">${statusText}</span>` : ''}
                        ${isOnline ? `<span class="connection-online-badge"><span class="online-dot"></span>Online</span>` : ''}
                    </div>
                    <div class="connection-details">
                        <span class="connection-badge">${getRelationEmoji(conn.relationship)} ${conn.relationship}</span>
                        <span style="opacity: 0.5;">•</span>
                        <span style="font-family: 'Space Grotesk', monospace; letter-spacing: 1px;">${conn.other_user_code || ''}</span>
                    </div>
                </div>
                <div class="connection-actions">
                    <button class="connection-btn connection-btn-direct" onclick="initiateDirectCall('${conn.other_user_id}', '${conn.other_user_name || 'Friend'}')" title="Call now">
                        📞
                    </button>
                    <button class="connection-btn connection-btn-call" onclick="openScheduleCallModal('${conn.connection_id}', '${conn.other_user_id}', '${conn.other_user_name}')" title="Schedule call">
                        ⏰
                    </button>
                </div>
            </div>
        `}).join('')}
    `;
}

function renderPendingRequests() {
    const list = document.getElementById('pendingRequestsList');
    const sentList = document.getElementById('sentRequestsList');
    
    // Incoming requests
    if (pendingRequests.length === 0) {
        list.innerHTML = `
            <div class="section-header">
                <span class="section-title">📬 Incoming Requests</span>
            </div>
            <div class="empty-state" style="padding: 30px 20px;">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-title">No pending requests</div>
                <div class="empty-state-text">When someone sends you a connection request, it will appear here</div>
            </div>
        `;
    } else {
        list.innerHTML = `
            <div class="section-header">
                <span class="section-title">📬 Incoming Requests</span>
                <span class="section-count">${pendingRequests.length}</span>
            </div>
            ${pendingRequests.map(req => `
                <div class="connection-card pending-card">
                    <div class="connection-avatar">
                        ${(req.other_user_name || 'U')[0].toUpperCase()}
                    </div>
                    <div class="connection-info">
                        <div class="connection-name">${req.other_user_name}</div>
                        <div class="pending-message">wants to connect as <strong>${req.relationship}</strong></div>
                    </div>
                    <div class="connection-actions">
                        <button class="connection-btn connection-btn-accept" onclick="respondToRequest('${req.connection_id}', true)">
                            ✓ Accept
                        </button>
                        <button class="connection-btn connection-btn-reject" onclick="respondToRequest('${req.connection_id}', false)">
                            ✕
                        </button>
                    </div>
                </div>
            `).join('')}
        `;
    }
    
    // Sent requests
    if (sentRequests.length > 0) {
        sentList.innerHTML = `
            <div class="section-header">
                <span class="section-title">📤 Sent Requests</span>
                <span class="section-count">${sentRequests.length}</span>
            </div>
            ${sentRequests.map(req => `
                <div class="connection-card" style="opacity: 0.7;">
                    <div class="connection-avatar" style="background: var(--surface);">
                        ${(req.other_user_name || 'U')[0].toUpperCase()}
                    </div>
                    <div class="connection-info">
                        <div class="connection-name">${req.other_user_name}</div>
                        <div class="connection-details">
                            <span style="color: var(--warning);">⏳ Pending...</span>
                        </div>
                    </div>
                </div>
            `).join('')}
        `;
    } else {
        sentList.innerHTML = '';
    }
}

function handleSearchKeyup(event) {
    if (event.key === 'Enter') {
        searchUserByCode();
    }
    // Auto-uppercase
    event.target.value = event.target.value.toUpperCase();
}

async function searchUserByCode() {
    const code = document.getElementById('connectCode').value.trim().toUpperCase();
    const resultDiv = document.getElementById('searchResult');
    const placeholder = document.getElementById('searchPlaceholder');
    const searchBtn = document.getElementById('searchBtn');
    
    console.log('Searching for code:', code);
    
    if (code.length < 4) {
        resultDiv.innerHTML = `
            <div class="search-not-found">
                <div class="search-not-found-icon">🔤</div>
                <p>Enter at least 4 characters</p>
            </div>
        `;
        resultDiv.style.display = 'block';
        placeholder.style.display = 'none';
        return;
    }
    
    // Show loading state
    searchBtn.classList.add('loading');
    searchBtn.innerHTML = '';
    resultDiv.style.display = 'none';
    placeholder.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/api/connections/find/${code}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        console.log('Search response:', response.status, data);
        
        if (data.found) {
            resultDiv.innerHTML = `
                <div class="user-found-card">
                    <div class="user-found-header">
                        <div class="user-found-avatar">
                            ${(data.user.name || 'U')[0].toUpperCase()}
                        </div>
                        <div class="user-found-info">
                            <div class="user-found-name">${data.user.name}</div>
                            <div class="user-found-code">${data.user.code}</div>
                        </div>
                    </div>
                    <div class="connect-form">
                        <select id="connectRelation" class="connect-relation-select">
                            <option value="family">👨‍👩‍👧 Family</option>
                            <option value="friend">🧑 Friend</option>
                            <option value="caregiver">💝 Caregiver</option>
                        </select>
                        <button class="send-request-btn" onclick="sendConnectionRequest('${data.user.id}', '${code}')" id="sendRequestBtn">
                            <span>🤝</span> Send Request
                        </button>
                    </div>
                </div>
            `;
        } else {
            resultDiv.innerHTML = `
                <div class="search-not-found">
                    <div class="search-not-found-icon">😕</div>
                    <p>${data.message || 'No user found with this code'}</p>
                </div>
            `;
        }
        resultDiv.style.display = 'block';
    } catch (e) {
        console.error('Search failed:', e);
        resultDiv.innerHTML = `
            <div class="search-error">
                ❌ Search failed. Please try again.
            </div>
        `;
        resultDiv.style.display = 'block';
    } finally {
        searchBtn.classList.remove('loading');
        searchBtn.innerHTML = '🔍';
    }
}

async function sendConnectionRequest(userId, code) {
    const relationship = document.getElementById('connectRelation').value;
    const btn = document.getElementById('sendRequestBtn');
    
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Sending...';
    
    try {
        const response = await fetch(`${API_BASE}/api/connections/request`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                code: code,
                relationship: relationship
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success
            btn.innerHTML = '<span>✓</span> Sent!';
            btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
            
            // Update UI after delay
            setTimeout(async () => {
                document.getElementById('searchResult').style.display = 'none';
                document.getElementById('searchPlaceholder').style.display = 'block';
                document.getElementById('connectCode').value = '';
                await loadConnections();
                
                // Show and switch to requests tab
                switchConnectionTab('requests');
            }, 1500);
        } else {
            btn.innerHTML = `<span>❌</span> ${data.message || 'Failed'}`;
            btn.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = '<span>🤝</span> Send Request';
                btn.style.background = '';
            }, 2000);
        }
    } catch (e) {
        console.error('Failed to send request:', e);
        btn.innerHTML = '<span>❌</span> Error';
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = '<span>🤝</span> Send Request';
            btn.style.background = '';
        }, 2000);
    }
}

async function respondToRequest(connectionId, accept) {
    // Find and update the button visually
    const card = event.target.closest('.connection-card');
    if (card) {
        card.style.opacity = '0.5';
        card.style.pointerEvents = 'none';
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/connections/${connectionId}/respond`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ accept })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show toast notification
            showToast(accept ? '🎉 Connected!' : 'Request declined', accept ? 'success' : 'info');
            await loadConnections();
            
            if (accept) {
                // Switch to connected tab
                setTimeout(() => switchConnectionTab('connected'), 500);
            }
        } else {
            showToast(data.message || 'Failed', 'error');
            if (card) {
                card.style.opacity = '1';
                card.style.pointerEvents = 'auto';
            }
        }
    } catch (e) {
        console.error('Failed to respond:', e);
        showToast('Failed to respond', 'error');
        if (card) {
            card.style.opacity = '1';
            card.style.pointerEvents = 'auto';
        }
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position: fixed;
        bottom: 30px;
        left: 50%;
        transform: translateX(-50%);
        padding: 14px 24px;
        background: ${type === 'success' ? 'linear-gradient(135deg, #22c55e, #16a34a)' : 
                     type === 'error' ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 
                     'var(--surface)'};
        color: white;
        border-radius: 14px;
        font-weight: 500;
        z-index: 10000;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        animation: toastIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

// ===== PRESENCE / ONLINE STATUS =====

async function loadConnectionsPresence() {
    try {
        const response = await fetch(`${API_BASE}/api/presence/connections`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        // Build presence map
        connectionsPresence = {};
        if (data.presence) {
            data.presence.forEach(p => {
                connectionsPresence[p.user_id] = p;
            });
        }
        
        // Re-render connections if panel is visible
        if (currentConnectionTab === 'connected') {
            renderConnections();
        }
    } catch (e) {
        console.log('Failed to load presence:', e);
    }
}

async function updateMyPresence(status, activity = null) {
    try {
        await fetch(`${API_BASE}/api/presence/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ status, activity })
        });
    } catch (e) {
        console.log('Failed to update presence:', e);
    }
}

function startPresenceTracking() {
    // Update presence immediately
    updateMyPresence('online', 'browsing');
    
    // Update presence every minute
    if (presenceInterval) clearInterval(presenceInterval);
    presenceInterval = setInterval(() => {
        updateMyPresence('online', room ? 'talking_to_synki' : 'browsing');
    }, 60000);
    
    // Update presence on visibility change
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            updateMyPresence('away');
        } else {
            updateMyPresence('online', room ? 'talking_to_synki' : 'browsing');
        }
    });
    
    // Update presence before leaving page
    window.addEventListener('beforeunload', () => {
        // Use sendBeacon for reliable delivery
        const data = JSON.stringify({ status: 'offline', activity: null });
        navigator.sendBeacon(`${API_BASE}/api/presence/update`, new Blob([data], { type: 'application/json' }));
    });
}

// ===== SCHEDULE CALL FOR CONNECTIONS =====

let scheduleConnectionId = null;
let scheduleTargetUserId = null;
let scheduleTargetUserName = null;

async function openScheduleCallModal(connectionId, userId, userName) {
    scheduleConnectionId = connectionId;
    scheduleTargetUserId = userId;
    scheduleTargetUserName = userName;
    
    // Load topics if not already loaded
    if (!callTopics || callTopics.length === 0) {
        await loadCallTopics();
    }
    
    // Create modal if doesn't exist, otherwise show it
    let modal = document.getElementById('connectionScheduleModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'connectionScheduleModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <span>📞</span>
                    <h2>Schedule Call</h2>
                    <button class="modal-close" onclick="closeConnectionScheduleModal()">✕</button>
                </div>
                <div class="modal-body">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <div style="width: 70px; height: 70px; border-radius: 50%; background: linear-gradient(135deg, var(--primary), var(--secondary)); display: flex; align-items: center; justify-content: center; color: white; font-size: 1.8rem; font-weight: 600; margin: 0 auto 12px;">
                            <span id="scheduleTargetInitial">U</span>
                        </div>
                        <div style="font-size: 1.2rem; font-weight: 600;" id="scheduleTargetName">User</div>
                        <div style="color: var(--text-secondary); font-size: 0.85rem;">Synki will call them at the scheduled time</div>
                    </div>
                    
                    <label class="search-label">When should Synki call?</label>
                    <div class="quick-options" style="margin-bottom: 16px;">
                        <button class="quick-btn" onclick="selectConnectionQuickTime(1)">1 min</button>
                        <button class="quick-btn" onclick="selectConnectionQuickTime(5)">5 min</button>
                        <button class="quick-btn" onclick="selectConnectionQuickTime(15)">15 min</button>
                        <button class="quick-btn" onclick="selectConnectionQuickTime(30)">30 min</button>
                        <button class="quick-btn" onclick="selectConnectionQuickTime(60)">1 hr</button>
                    </div>
                    
                    <label class="search-label">Custom time (minutes):</label>
                    <input type="number" class="time-input" id="connectionCallMinutes" min="1" max="1440" value="10" style="margin-bottom: 16px;">
                    
                    <label class="search-label">What should Synki ask about?</label>
                    <select class="time-input" id="connectionCallTopic" style="margin-bottom: 16px;" onchange="toggleCustomQuestion()">
                        <option value="">💕 General Check-in</option>
                        <option value="custom">✏️ Custom Question</option>
                    </select>
                    
                    <div id="customQuestionSection" style="display: none;">
                        <label class="search-label">What should Synki ask?</label>
                        <input type="text" class="time-input" id="connectionCallCustomQuestion" placeholder="e.g. Did you take your medicine today?" style="margin-bottom: 16px;">
                    </div>
                    
                    <button class="modal-confirm" onclick="confirmConnectionCall()" id="confirmConnectionCallBtn">
                        📞 Schedule Call
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    // Update modal content
    document.getElementById('scheduleTargetInitial').textContent = (userName || 'U')[0].toUpperCase();
    document.getElementById('scheduleTargetName').textContent = userName;
    
    // Load topics into dropdown
    const topicSelect = document.getElementById('connectionCallTopic');
    topicSelect.innerHTML = '<option value="">💕 General Check-in</option><option value="custom">✏️ Custom Question</option>';
    if (callTopics && callTopics.length > 0) {
        callTopics.forEach(topic => {
            const emoji = topic.emoji || '💬';
            topicSelect.innerHTML += `<option value="${topic.id}" data-prompts='${JSON.stringify(topic.prompts || [])}'>${emoji} ${topic.title}</option>`;
        });
    }
    
    // Reset custom question section
    const customSection = document.getElementById('customQuestionSection');
    if (customSection) customSection.style.display = 'none';
    
    // Show modal
    modal.classList.remove('hidden');
}

function closeConnectionScheduleModal() {
    const modal = document.getElementById('connectionScheduleModal');
    if (modal) modal.classList.add('hidden');
    scheduleConnectionId = null;
    scheduleTargetUserId = null;
    scheduleTargetUserName = null;
}

function selectConnectionQuickTime(minutes) {
    document.getElementById('connectionCallMinutes').value = minutes;
    // Highlight selected button
    document.querySelectorAll('#connectionScheduleModal .quick-btn').forEach(btn => btn.classList.remove('selected'));
    event.target.classList.add('selected');
}

function toggleCustomQuestion() {
    const select = document.getElementById('connectionCallTopic');
    const customSection = document.getElementById('customQuestionSection');
    if (select.value === 'custom') {
        customSection.style.display = 'block';
    } else {
        customSection.style.display = 'none';
    }
}

async function confirmConnectionCall() {
    if (!scheduleConnectionId) return;
    
    const minutes = parseInt(document.getElementById('connectionCallMinutes').value) || 10;
    const topicSelect = document.getElementById('connectionCallTopic');
    const topicValue = topicSelect.value;
    
    // Get topic prompts
    let topicPrompts = [];
    let topicTitle = 'check-in';
    
    if (topicValue === 'custom') {
        // Custom question entered by user
        const customQuestion = document.getElementById('connectionCallCustomQuestion').value.trim();
        if (customQuestion) {
            topicPrompts = [customQuestion];
            topicTitle = 'Custom Question';
        }
    } else if (topicValue) {
        // Preset topic selected
        const selectedOption = topicSelect.options[topicSelect.selectedIndex];
        try {
            topicPrompts = JSON.parse(selectedOption.dataset.prompts || '[]');
            topicTitle = selectedOption.textContent;
        } catch (e) {
            console.error('Failed to parse topic prompts:', e);
        }
    }
    
    // Calculate scheduled time
    const scheduledAt = new Date(Date.now() + minutes * 60000).toISOString();
    
    const btn = document.getElementById('confirmConnectionCallBtn');
    btn.disabled = true;
    btn.innerHTML = '⏳ Scheduling...';
    
    console.log('📋 Scheduling call with:', { topicTitle, topicPrompts });
    
    try {
        const response = await fetch(`${API_BASE}/api/connections/${scheduleConnectionId}/schedule-call`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({
                scheduled_at: scheduledAt,
                message: topicTitle !== 'check-in' ? `📋 ${topicTitle}` : `Hey ${scheduleTargetUserName}! Synki is calling 💕`,
                topic_id: topicValue && topicValue !== 'custom' ? topicValue : null,
                topic_prompts: topicPrompts
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            btn.innerHTML = '✓ Scheduled!';
            btn.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
            
            showToast(`📞 Call scheduled for ${scheduleTargetUserName} in ${minutes} min!`, 'success');
            
            setTimeout(() => {
                closeConnectionScheduleModal();
                closeConnectionsModal();
                btn.disabled = false;
                btn.innerHTML = '📞 Schedule Call';
                btn.style.background = '';
            }, 1500);
        } else {
            throw new Error(data.message || 'Failed to schedule');
        }
    } catch (e) {
        console.error('Failed to schedule call:', e);
        btn.innerHTML = '❌ Failed';
        btn.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
        showToast(e.message || 'Failed to schedule call', 'error');
        
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = '📞 Schedule Call';
            btn.style.background = '';
        }, 2000);
    }
}

// Keep original function for backward compatibility
async function scheduleCallFor(userId, userName) {
    // Find connection ID for this user
    const conn = myConnections.find(c => c.other_user_id === userId);
    if (conn) {
        openScheduleCallModal(conn.connection_id, userId, userName);
    } else {
        closeConnectionsModal();
        openScheduleModal();
        showToast(`📞 Scheduling call with ${userName}`, 'info');
    }
}

function checkExistingSchedule() {
    const storedTime = localStorage.getItem('scheduledCallTime');
    const storedId = localStorage.getItem('scheduledCallId');
    
    if (storedTime) {
        const time = parseInt(storedTime);
        if (time > Date.now()) {
            scheduledCallTime = time;
            scheduledCallId = storedId;
            
            document.getElementById('scheduledIndicator').style.display = 'flex';
            document.getElementById('scheduleCallBtn').style.display = 'none';
            
            updateScheduleCountdown();
            scheduledCallInterval = setInterval(updateScheduleCountdown, 1000);
            scheduledCallTimeout = setTimeout(triggerScheduledCall, (time - Date.now()) + 30000);
        } else {
            localStorage.removeItem('scheduledCallTime');
            localStorage.removeItem('scheduledCallId');
        }
    }
}

// ===== CALL HISTORY FUNCTIONS =====
async function openCallHistory() {
    document.getElementById('callHistoryModal').classList.remove('hidden');
    await loadCallHistory();
}

function closeCallHistory() {
    document.getElementById('callHistoryModal').classList.add('hidden');
}

async function loadCallHistory() {
    if (!currentUser) return;
    
    try {
        const response = await fetch(`${API_BASE}/sessions/${currentUser.id}?limit=20`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        const list = document.getElementById('callHistoryList');
        
        if (!data.sessions || data.sessions.length === 0) {
            list.innerHTML = `
                <div class="call-history-empty">
                    <span style="font-size: 2rem;">📞</span>
                    <p>No calls yet. Start a conversation!</p>
                </div>`;
            return;
        }
        
        list.innerHTML = data.sessions.map(s => {
            const date = new Date(s.started_at);
            const timeAgo = formatTimeAgo(date);
            const duration = formatDuration(s.duration_seconds);
            const turns = s.turn_count || 0;
            
            return `
                <div class="call-history-item">
                    <div class="call-item-icon">📞</div>
                    <div class="call-item-details">
                        <div class="call-item-name">Synki 💕 ${turns > 0 ? `<span style="font-size:0.7rem;background:rgba(255,107,157,0.2);padding:2px 6px;border-radius:10px;">${turns} msgs</span>` : ''}</div>
                        <div class="call-item-time">${timeAgo}</div>
                    </div>
                    <div class="call-item-duration">${duration}</div>
                </div>`;
        }).join('');
    } catch (error) {
        console.error('Failed to load call history:', error);
    }
}

function formatTimeAgo(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hr ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    
    return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// ===== SETTINGS FUNCTIONS =====
let autoReplySettings = {
    auto_reply_enabled: false,
    auto_reply_message: 'Main abhi busy hoon, please message chhod do',
    auto_reply_voice: 'sweet',
    auto_reply_when: 'offline'
};

// Settings modal removed - Settings tab is the new design
async function loadAutoReplySettings() {
    try {
        const response = await fetch(`${API_BASE}/api/settings/auto-reply`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        if (data.success !== false) {
            autoReplySettings = data;
            
            // Update UI
            document.getElementById('autoReplyEnabled').checked = data.auto_reply_enabled || false;
            document.getElementById('autoReplyMessage').value = data.auto_reply_message || '';
            document.getElementById('autoReplyWhen').value = data.auto_reply_when || 'offline';
            document.getElementById('autoReplyVoice').value = data.auto_reply_voice || 'sweet';
            
            // Show/hide options based on toggle
            document.getElementById('autoReplyOptions').style.display = data.auto_reply_enabled ? 'block' : 'none';
        }
    } catch (e) {
        console.error('Failed to load auto-reply settings:', e);
    }
}

async function saveAutoReplySettings() {
    const enabled = document.getElementById('autoReplyEnabled').checked;
    
    // Show/hide options
    document.getElementById('autoReplyOptions').style.display = enabled ? 'block' : 'none';
    
    const settings = {
        auto_reply_enabled: enabled,
        auto_reply_message: document.getElementById('autoReplyMessage').value || 'Main abhi busy hoon',
        auto_reply_when: document.getElementById('autoReplyWhen').value,
        auto_reply_voice: document.getElementById('autoReplyVoice').value
    };
    
    console.log('📱 Saving auto-reply settings:', settings);
    
    const status = document.getElementById('settingsSaveStatus');
    
    try {
        const response = await fetch(`${API_BASE}/api/settings/auto-reply`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        console.log('📱 Save response:', data);
        
        if (response.ok && data.success) {
            // Show success status
            status.textContent = '✓ Settings saved!';
            status.style.color = 'var(--success)';
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 2000);
            
            autoReplySettings = settings;
        } else {
            // Show error
            status.textContent = '❌ Failed to save: ' + (data.detail || 'Unknown error');
            status.style.color = '#ef4444';
            status.style.display = 'block';
            setTimeout(() => { status.style.display = 'none'; }, 3000);
        }
    } catch (e) {
        console.error('Failed to save auto-reply settings:', e);
        status.textContent = '❌ Network error: ' + e.message;
        status.style.color = '#ef4444';
        status.style.display = 'block';
        setTimeout(() => { status.style.display = 'none'; }, 3000);
    }
}

async function updateMyStatus() {
    const status = document.getElementById('myStatus').value;
    try {
        await fetch(`${API_BASE}/api/presence/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ status, activity: 'manual_set' })
        });
    } catch (e) {
        console.error('Failed to update status:', e);
    }
}

async function loadAutoReplyMessages() {
    const container = document.getElementById('autoReplyMessagesList');
    
    try {
        const response = await fetch(`${API_BASE}/api/messages/auto-reply`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        const data = await response.json();
        
        // Update badge
        const badge = document.getElementById('messagesUnreadBadge');
        if (data.unread_count > 0) {
            badge.textContent = data.unread_count;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
        
        if (!data.messages || data.messages.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 20px; color: var(--text-muted);">
                    No messages yet
                </div>
            `;
            return;
        }
        
        container.innerHTML = data.messages.map(msg => `
            <div style="padding: 12px; background: ${msg.is_read ? 'var(--surface)' : 'rgba(160,82,45,0.1)'}; border-radius: 12px; margin-bottom: 8px; ${!msg.is_read ? 'border-left: 3px solid var(--primary);' : ''} cursor: pointer;"
                 onclick="markMessageRead('${msg.id}', this)">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-weight: 600; color: var(--text-primary);">${msg.caller_name || 'Someone'}</span>
                    <span style="font-size: 0.75rem; color: var(--text-muted);">${new Date(msg.created_at).toLocaleString()}</span>
                </div>
                <div style="color: var(--text-secondary); font-size: 0.9rem;">${msg.message}</div>
                ${msg.is_urgent ? '<span style="color: var(--error); font-size: 0.75rem;">🔴 Urgent</span>' : ''}
            </div>
        `).join('');
        
    } catch (e) {
        console.error('Failed to load messages:', e);
        container.innerHTML = `
            <div style="text-align: center; padding: 20px; color: var(--text-muted);">
                Failed to load messages
            </div>
        `;
    }
}

async function markMessageRead(messageId, element) {
    try {
        await fetch(`${API_BASE}/api/messages/auto-reply/${messageId}/read`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        
        // Update UI
        element.style.background = 'var(--surface)';
        element.style.borderLeft = 'none';
        
        // Refresh badge
        loadAutoReplyMessages();
    } catch (e) {
        console.error('Failed to mark message read:', e);
    }
}

// ===== SERVICE WORKER MESSAGE HANDLER =====
// Handle messages from service worker (e.g., when user clicks Accept on notification)
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (event) => {
        console.log('📬 Message from service worker:', event.data);
        
        if (event.data.type === 'ACCEPT_CALL') {
            // Auto-connect when user accepts call from notification
            if (!room && connectBtn && !connectBtn.disabled) {
                console.log('📞 Auto-connecting from notification accept...');
                connectBtn.click();
            }
        }
    });
}

// Check URL parameters for auto-actions (when opened from notification)
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('action') === 'accept') {
    // Auto-connect after page loads and user is logged in
    setTimeout(() => {
        if (currentUser && !room && connectBtn && !connectBtn.disabled) {
            console.log('📞 Auto-connecting from notification URL...');
            connectBtn.click();
        }
    }, 2000);
}

// Check for existing schedule on page load
setTimeout(checkExistingSchedule, 1000);

init();
