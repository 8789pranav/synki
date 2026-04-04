/**
 * Synki LiveKit Module
 * Handles voice connection with LiveKit
 */

// Logger utility
const Logger = {
    log: (module, message, data = null) => {
        const timestamp = new Date().toLocaleTimeString();
        const prefix = `[${timestamp}] [${module}]`;
        if (data) {
            console.log(`${prefix} ${message}`, data);
        } else {
            console.log(`${prefix} ${message}`);
        }
        // Also show in UI if debug panel exists
        const debugPanel = document.getElementById('debug-log');
        if (debugPanel) {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `<span class="log-time">${timestamp}</span> <span class="log-module">[${module}]</span> ${message}`;
            debugPanel.appendChild(entry);
            debugPanel.scrollTop = debugPanel.scrollHeight;
        }
    },
    error: (module, message, error = null) => {
        const timestamp = new Date().toLocaleTimeString();
        console.error(`[${timestamp}] [${module}] ❌ ${message}`, error || '');
        const debugPanel = document.getElementById('debug-log');
        if (debugPanel) {
            const entry = document.createElement('div');
            entry.className = 'log-entry log-error';
            entry.innerHTML = `<span class="log-time">${timestamp}</span> <span class="log-module">[${module}]</span> ❌ ${message}`;
            debugPanel.appendChild(entry);
            debugPanel.scrollTop = debugPanel.scrollHeight;
        }
    }
};

const LiveKit = {
    room: null,
    isConnected: false,
    
    // Callbacks
    onConnectionChange: null,
    onMessage: null,
    onEmotion: null,
    onSpeakingChange: null,

    /**
     * Connect to LiveKit room
     */
    async connect(userId) {
        if (this.isConnected) {
            Logger.log('LiveKit', '⚠️ Already connected');
            return;
        }
        
        try {
            Logger.log('LiveKit', '🔄 Starting connection...', { userId });
            
            // Get token from API
            const roomName = `synki-${userId}`;
            Logger.log('LiveKit', '🎫 Requesting token...', { roomName });
            
            const tokenData = await API.getLiveKitToken(userId, roomName);
            
            if (!tokenData.token) {
                throw new Error('Failed to get connection token');
            }
            
            Logger.log('LiveKit', '✅ Token received', { 
                room: tokenData.room_name,
                url: tokenData.url 
            });
            
            // Create room instance
            Logger.log('LiveKit', '🏠 Creating room instance...');
            this.room = new LivekitClient.Room({
                adaptiveStream: true,
                dynacast: true,
            });
            
            // Set up event handlers
            this.setupEventHandlers();
            
            // Connect to room
            Logger.log('LiveKit', '🔌 Connecting to LiveKit server...');
            await this.room.connect(CONFIG.LIVEKIT_URL, tokenData.token);
            Logger.log('LiveKit', '✅ Connected to room!');
            
            // Enable microphone
            Logger.log('LiveKit', '🎤 Enabling microphone...');
            await this.room.localParticipant.setMicrophoneEnabled(true);
            Logger.log('LiveKit', '✅ Microphone enabled');
            
            this.isConnected = true;
            this.notifyConnectionChange(true);
            
            Logger.log('LiveKit', '🎉 Fully connected! Waiting for agent...');
            
            return true;
        } catch (error) {
            Logger.error('LiveKit', 'Connection failed', error);
            this.isConnected = false;
            this.notifyConnectionChange(false, error.message);
            throw error;
        }
    },

    /**
     * Disconnect from LiveKit room
     */
    async disconnect() {
        if (this.room) {
            await this.room.disconnect();
            this.room = null;
        }
        
        this.isConnected = false;
        this.notifyConnectionChange(false);
    },

    /**
     * Set up LiveKit event handlers
     */
    setupEventHandlers() {
        if (!this.room) return;
        
        Logger.log('LiveKit', '📡 Setting up event handlers...');
        
        // Participant connected (agent joins)
        this.room.on(LivekitClient.RoomEvent.ParticipantConnected, (participant) => {
            Logger.log('LiveKit', '👤 Participant joined!', { 
                identity: participant.identity,
                name: participant.name 
            });
        });
        
        // Participant disconnected
        this.room.on(LivekitClient.RoomEvent.ParticipantDisconnected, (participant) => {
            Logger.log('LiveKit', '👤 Participant left', { identity: participant.identity });
        });
        
        // Track subscribed (audio from agent)
        this.room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, publication, participant) => {
            Logger.log('LiveKit', '🔊 Track subscribed!', { 
                kind: track.kind,
                participant: participant.identity 
            });
            
            if (track.kind === 'audio') {
                // Attach audio to DOM
                const audioEl = track.attach();
                audioEl.id = 'synki-audio';
                document.body.appendChild(audioEl);
                
                Logger.log('LiveKit', '🔈 Agent audio attached!');
                
                // Notify speaking started
                this.notifySpeakingChange(true);
                
                // Listen for track end
                track.on('ended', () => {
                    Logger.log('LiveKit', '🔇 Agent audio ended');
                    this.notifySpeakingChange(false);
                });
            }
        });
        
        // Track published (agent starts publishing)
        this.room.on(LivekitClient.RoomEvent.TrackPublished, (publication, participant) => {
            Logger.log('LiveKit', '📢 Track published', { 
                kind: publication.kind,
                participant: participant.identity 
            });
        });
        
        // Track unsubscribed
        this.room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
            Logger.log('LiveKit', '🔕 Track unsubscribed', { kind: track.kind });
            if (track.kind === 'audio') {
                track.detach();
                const audioEl = document.getElementById('synki-audio');
                if (audioEl) audioEl.remove();
            }
        });
        
        // Connection quality
        this.room.on(LivekitClient.RoomEvent.ConnectionQualityChanged, (quality, participant) => {
            Logger.log('LiveKit', '📶 Connection quality', { 
                quality, 
                participant: participant.identity 
            });
        });
        
        // Disconnected
        this.room.on(LivekitClient.RoomEvent.Disconnected, (reason) => {
            Logger.log('LiveKit', '🔌 Disconnected', { reason });
            this.isConnected = false;
            this.notifyConnectionChange(false);
        });
        
        // Data received (transcripts, emotions, etc.)
        this.room.on(LivekitClient.RoomEvent.DataReceived, (data, participant) => {
            Logger.log('LiveKit', '📨 Data received from', { participant: participant?.identity });
            this.handleDataMessage(data);
        });
        
        // Active speakers changed
        this.room.on(LivekitClient.RoomEvent.ActiveSpeakersChanged, (speakers) => {
            const speakerNames = speakers.map(s => s.identity);
            if (speakerNames.length > 0) {
                Logger.log('LiveKit', '🗣️ Active speakers', { speakers: speakerNames });
            }
        });
        
        Logger.log('LiveKit', '✅ Event handlers set up');
    },

    /**
     * Handle incoming data messages
     */
    handleDataMessage(data) {
        try {
            const decoder = new TextDecoder();
            const message = JSON.parse(decoder.decode(data));
            
            switch (message.type) {
                case 'transcript':
                    if (this.onMessage) {
                        this.onMessage(message.role, message.text);
                    }
                    break;
                    
                case 'emotion':
                    if (this.onEmotion) {
                        this.onEmotion(message.emotion);
                    }
                    break;
                    
                case 'memory_update':
                    // Trigger memory reload
                    if (this.onMessage) {
                        this.onMessage('system', '🧠 Memory updated!');
                    }
                    break;
                    
                default:
                    console.log('Unknown message type:', message.type);
            }
        } catch (e) {
            console.log('Failed to parse data message:', e);
        }
    },

    /**
     * Notify connection change
     */
    notifyConnectionChange(connected, error = null) {
        if (this.onConnectionChange) {
            this.onConnectionChange(connected, error);
        }
    },

    /**
     * Notify speaking state change
     */
    notifySpeakingChange(speaking) {
        if (this.onSpeakingChange) {
            this.onSpeakingChange(speaking);
        }
    }
};
