/**
 * Synki Main Application
 * Coordinates all modules and handles UI interactions
 */

const App = {
    // DOM Elements
    elements: {},

    /**
     * Initialize the application
     */
    async init() {
        // Cache DOM elements
        this.cacheElements();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Set up LiveKit callbacks
        this.setupLiveKitCallbacks();
        
        // Check for existing session
        const hasSession = Auth.init();
        
        if (hasSession) {
            // Verify session is still valid
            const isValid = await Auth.verifySession();
            
            if (isValid) {
                this.showApp();
                this.loadUserData();
            } else {
                this.showAuth();
            }
        } else {
            this.showAuth();
        }
        
        // Hide loading screen
        setTimeout(() => {
            this.elements.loadingScreen.classList.add('fade-out');
        }, CONFIG.UI.LOADING_DELAY);
    },

    /**
     * Cache DOM elements
     */
    cacheElements() {
        this.elements = {
            // Loading
            loadingScreen: document.getElementById('loadingScreen'),
            
            // Auth
            authSection: document.getElementById('authSection'),
            loginForm: document.getElementById('loginForm'),
            signupForm: document.getElementById('signupForm'),
            authError: document.getElementById('authError'),
            authErrorText: document.getElementById('authErrorText'),
            loginBtn: document.getElementById('loginBtn'),
            signupBtn: document.getElementById('signupBtn'),
            showSignup: document.getElementById('showSignup'),
            showLogin: document.getElementById('showLogin'),
            
            // App
            appSection: document.getElementById('appSection'),
            userAvatar: document.getElementById('userAvatar'),
            userName: document.getElementById('userName'),
            userEmail: document.getElementById('userEmail'),
            logoutBtn: document.getElementById('logoutBtn'),
            
            // Avatar
            avatar: document.getElementById('avatar'),
            avatarRing: document.querySelector('.avatar-ring'),
            avatarStatus: document.getElementById('avatarStatus'),
            emotionBadge: document.getElementById('emotionBadge'),
            
            // Connection
            connectBtn: document.getElementById('connectBtn'),
            disconnectBtn: document.getElementById('disconnectBtn'),
            micIndicator: document.getElementById('micIndicator'),
            
            // Chat
            chatMessages: document.getElementById('chatMessages'),
            
            // Memories
            memoriesList: document.getElementById('memoriesList'),
            
            // Status
            statusBar: document.getElementById('statusBar')
        };
    },

    /**
     * Set up event listeners
     */
    setupEventListeners() {
        // Auth form switching
        this.elements.showSignup.addEventListener('click', (e) => {
            e.preventDefault();
            this.elements.loginForm.classList.add('hidden');
            this.elements.signupForm.classList.remove('hidden');
            this.hideAuthError();
        });
        
        this.elements.showLogin.addEventListener('click', (e) => {
            e.preventDefault();
            this.elements.signupForm.classList.add('hidden');
            this.elements.loginForm.classList.remove('hidden');
            this.hideAuthError();
        });
        
        // Login form
        this.elements.loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });
        
        // Signup form
        this.elements.signupForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSignup();
        });
        
        // Logout
        this.elements.logoutBtn.addEventListener('click', () => {
            this.handleLogout();
        });
        
        // Connect
        this.elements.connectBtn.addEventListener('click', () => {
            this.handleConnect();
        });
        
        // Disconnect
        this.elements.disconnectBtn.addEventListener('click', () => {
            this.handleDisconnect();
        });
    },

    /**
     * Set up LiveKit callbacks
     */
    setupLiveKitCallbacks() {
        LiveKit.onConnectionChange = (connected, error) => {
            this.updateConnectionUI(connected);
            if (error) {
                this.updateStatus('error', `Connection failed: ${error}`);
            }
        };
        
        LiveKit.onMessage = (role, text) => {
            this.addMessage(role, text);
        };
        
        LiveKit.onEmotion = (emotion) => {
            this.updateEmotion(emotion);
        };
        
        LiveKit.onSpeakingChange = (speaking) => {
            this.updateSpeakingUI(speaking);
        };
    },

    /**
     * Handle login
     */
    async handleLogin() {
        const email = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value;
        
        this.setButtonLoading(this.elements.loginBtn, true, 'Logging in...');
        this.hideAuthError();
        
        try {
            await Auth.signin(email, password);
            this.showApp();
            this.loadUserData();
        } catch (error) {
            this.showAuthError(error.message);
        } finally {
            this.setButtonLoading(this.elements.loginBtn, false, 'Login');
        }
    },

    /**
     * Handle signup
     */
    async handleSignup() {
        const name = document.getElementById('signupName').value.trim();
        const email = document.getElementById('signupEmail').value.trim();
        const password = document.getElementById('signupPassword').value;
        
        this.setButtonLoading(this.elements.signupBtn, true, 'Creating account...');
        this.hideAuthError();
        
        try {
            await Auth.signup(name, email, password);
            this.showApp();
            this.loadUserData();
        } catch (error) {
            this.showAuthError(error.message);
        } finally {
            this.setButtonLoading(this.elements.signupBtn, false, 'Create Account');
        }
    },

    /**
     * Handle logout
     */
    async handleLogout() {
        await LiveKit.disconnect();
        await Auth.signout();
        this.showAuth();
        this.resetAppUI();
    },

    /**
     * Handle connect to voice
     */
    async handleConnect() {
        this.setButtonLoading(this.elements.connectBtn, true, 'Connecting...');
        this.updateStatus('default', 'Connecting...');
        
        try {
            await LiveKit.connect(Auth.currentUser.id);
            this.addMessage('system', '💕 Connected! Start talking to Synki...');
            this.updateStatus('connected', 'Connected');
        } catch (error) {
            this.addMessage('system', '❌ Failed to connect. Please try again.');
            this.updateStatus('error', 'Connection failed');
        } finally {
            this.setButtonLoading(this.elements.connectBtn, false, 'Start Talking');
        }
    },

    /**
     * Handle disconnect from voice
     */
    async handleDisconnect() {
        await LiveKit.disconnect();
        this.addMessage('system', '👋 Disconnected. Talk to you soon!');
        this.updateStatus('default', 'Disconnected');
    },

    /**
     * Show auth section
     */
    showAuth() {
        this.elements.authSection.classList.remove('hidden');
        this.elements.appSection.classList.add('hidden');
    },

    /**
     * Show app section
     */
    showApp() {
        this.elements.authSection.classList.add('hidden');
        this.elements.appSection.classList.remove('hidden');
        
        // Update user info in header
        const user = Auth.currentUser;
        this.elements.userName.textContent = user.name || 'Baby';
        this.elements.userEmail.textContent = user.email;
        this.elements.userAvatar.textContent = (user.name || 'U')[0].toUpperCase();
    },

    /**
     * Load user data (memories, etc.)
     */
    async loadUserData() {
        try {
            const memories = await API.getMemories(Auth.currentUser.id);
            this.displayMemories(memories);
        } catch (error) {
            console.log('No memories yet');
        }
    },

    /**
     * Display memories in UI
     */
    displayMemories(data) {
        const items = [];
        
        if (data.name) {
            items.push({ icon: '👤', text: `Name: ${data.name}` });
        }
        
        if (data.facts && data.facts.length > 0) {
            data.facts.slice(-CONFIG.UI.MEMORIES_MAX_DISPLAY).forEach(fact => {
                items.push({ icon: '✨', text: fact });
            });
        }
        
        if (items.length === 0) {
            this.elements.memoriesList.innerHTML = `
                <div class="memory-item">
                    <span class="memory-icon">✨</span>
                    <span class="memory-text">Getting to know you...</span>
                </div>
            `;
        } else {
            this.elements.memoriesList.innerHTML = items.map(item => `
                <div class="memory-item">
                    <span class="memory-icon">${item.icon}</span>
                    <span class="memory-text">${item.text}</span>
                </div>
            `).join('');
        }
    },

    /**
     * Add message to chat
     */
    addMessage(role, text) {
        const messageEl = document.createElement('div');
        
        if (role === 'system') {
            messageEl.className = 'message message-system';
            messageEl.innerHTML = `
                <span class="message-icon">💕</span>
                <span class="message-text">${text}</span>
            `;
        } else if (role === 'user') {
            messageEl.className = 'message message-user';
            messageEl.textContent = text;
        } else {
            messageEl.className = 'message message-assistant';
            messageEl.textContent = text;
        }
        
        this.elements.chatMessages.appendChild(messageEl);
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
    },

    /**
     * Update emotion display
     */
    updateEmotion(emotion) {
        const emotionData = CONFIG.EMOTIONS[emotion] || CONFIG.EMOTIONS.neutral;
        
        this.elements.emotionBadge.innerHTML = `
            <span class="emotion-icon">${emotionData.icon}</span>
            <span class="emotion-text">${emotionData.text}</span>
        `;
    },

    /**
     * Update connection UI
     */
    updateConnectionUI(connected) {
        if (connected) {
            this.elements.connectBtn.classList.add('hidden');
            this.elements.disconnectBtn.classList.remove('hidden');
            this.elements.micIndicator.classList.add('active');
            this.elements.micIndicator.querySelector('.mic-text').textContent = 'Microphone On';
            this.elements.avatarRing.classList.add('listening');
            this.elements.avatarStatus.textContent = 'Listening...';
        } else {
            this.elements.connectBtn.classList.remove('hidden');
            this.elements.disconnectBtn.classList.add('hidden');
            this.elements.micIndicator.classList.remove('active');
            this.elements.micIndicator.querySelector('.mic-text').textContent = 'Microphone Off';
            this.elements.avatarRing.classList.remove('listening', 'speaking');
            this.elements.avatarStatus.textContent = 'Ready to talk';
        }
    },

    /**
     * Update speaking UI
     */
    updateSpeakingUI(speaking) {
        if (speaking) {
            this.elements.avatarRing.classList.remove('listening');
            this.elements.avatarRing.classList.add('speaking');
            this.elements.avatarStatus.textContent = 'Speaking...';
        } else {
            this.elements.avatarRing.classList.remove('speaking');
            this.elements.avatarRing.classList.add('listening');
            this.elements.avatarStatus.textContent = 'Listening...';
        }
    },

    /**
     * Update status bar
     */
    updateStatus(type, text) {
        this.elements.statusBar.className = 'status-bar';
        
        if (type === 'connected') {
            this.elements.statusBar.classList.add('connected');
        } else if (type === 'error') {
            this.elements.statusBar.classList.add('error');
        }
        
        this.elements.statusBar.querySelector('.status-text').textContent = text;
    },

    /**
     * Show auth error
     */
    showAuthError(message) {
        this.elements.authErrorText.textContent = message;
        this.elements.authError.classList.add('show');
    },

    /**
     * Hide auth error
     */
    hideAuthError() {
        this.elements.authError.classList.remove('show');
    },

    /**
     * Set button loading state
     */
    setButtonLoading(button, loading, text) {
        button.disabled = loading;
        button.querySelector('.btn-text').textContent = text;
    },

    /**
     * Reset app UI to initial state
     */
    resetAppUI() {
        this.elements.chatMessages.innerHTML = `
            <div class="message message-system">
                <span class="message-icon">💕</span>
                <span class="message-text">Connect to start chatting with Synki!</span>
            </div>
        `;
        
        this.elements.memoriesList.innerHTML = `
            <div class="memory-item">
                <span class="memory-icon">✨</span>
                <span class="memory-text">Getting to know you...</span>
            </div>
        `;
        
        this.updateConnectionUI(false);
        this.updateStatus('default', 'Disconnected');
        this.updateEmotion('neutral');
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
