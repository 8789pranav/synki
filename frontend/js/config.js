/**
 * Synki Configuration
 */

const CONFIG = {
    // API Configuration
    API_BASE: 'http://localhost:8000',
    
    // LiveKit Configuration
    LIVEKIT_URL: 'wss://zupki-hv3uw8fv.livekit.cloud',
    
    // Storage Keys
    STORAGE_KEYS: {
        TOKEN: 'synki_token',
        USER: 'synki_user'
    },
    
    // UI Settings
    UI: {
        LOADING_DELAY: 1000,
        MESSAGE_MAX_LENGTH: 500,
        MEMORIES_MAX_DISPLAY: 10
    },
    
    // Emotions mapping
    EMOTIONS: {
        happy: { icon: '😊', text: 'Happy' },
        sad: { icon: '😢', text: 'Sad' },
        excited: { icon: '🤩', text: 'Excited' },
        loving: { icon: '🥰', text: 'Loving' },
        worried: { icon: '😟', text: 'Worried' },
        playful: { icon: '😜', text: 'Playful' },
        curious: { icon: '🤔', text: 'Curious' },
        neutral: { icon: '😌', text: 'Relaxed' }
    }
};

// Freeze config to prevent modifications
Object.freeze(CONFIG);
Object.freeze(CONFIG.STORAGE_KEYS);
Object.freeze(CONFIG.UI);
Object.freeze(CONFIG.EMOTIONS);
