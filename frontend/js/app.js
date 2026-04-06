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
                // Check for existing scheduled call
                this.checkExistingSchedule();
            } else {
                this.showAuth();
            }
        } else {
            this.showAuth();
        }
        
        // Request notification permission
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
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
            
            // Call History
            callHistoryList: document.getElementById('callHistoryList'),
            headerCallBtn: document.getElementById('headerCallBtn'),
            
            // Schedule Call
            scheduleCallBtn: document.getElementById('scheduleCallBtn'),
            scheduleModal: document.getElementById('scheduleModal'),
            closeScheduleModal: document.getElementById('closeScheduleModal'),
            quickBtns: document.querySelectorAll('.quick-btn'),
            customMinutes: document.getElementById('customMinutes'),
            confirmScheduleBtn: document.getElementById('confirmScheduleBtn'),
            scheduledIndicator: document.getElementById('scheduledIndicator'),
            scheduledCountdown: document.getElementById('scheduledCountdown'),
            cancelScheduleBtn: document.getElementById('cancelScheduleBtn'),
            
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
        
        // Header call button
        this.elements.headerCallBtn.addEventListener('click', () => {
            if (LiveKit.connected) {
                this.handleDisconnect();
            } else {
                this.handleConnect();
            }
        });
        
        // Schedule call button - open modal
        this.elements.scheduleCallBtn.addEventListener('click', () => {
            this.openScheduleModal();
        });
        
        // Close schedule modal
        this.elements.closeScheduleModal.addEventListener('click', () => {
            this.closeScheduleModal();
        });
        
        // Close modal on overlay click
        this.elements.scheduleModal.addEventListener('click', (e) => {
            if (e.target === this.elements.scheduleModal) {
                this.closeScheduleModal();
            }
        });
        
        // Quick time buttons
        this.elements.quickBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Remove selected from all
                this.elements.quickBtns.forEach(b => b.classList.remove('selected'));
                // Add selected to clicked
                btn.classList.add('selected');
                // Update custom input
                this.elements.customMinutes.value = btn.dataset.minutes;
            });
        });
        
        // Confirm schedule button
        this.elements.confirmScheduleBtn.addEventListener('click', () => {
            this.scheduleCall();
        });
        
        // Cancel scheduled call
        this.elements.cancelScheduleBtn.addEventListener('click', () => {
            this.cancelScheduledCall();
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
     * Load user data (memories, call history, etc.)
     */
    async loadUserData() {
        try {
            const memories = await API.getMemories(Auth.currentUser.id);
            this.displayMemories(memories);
        } catch (error) {
            console.log('No memories yet');
        }
        
        // Load call history
        try {
            const historyData = await API.getCallHistory(Auth.currentUser.id, 10);
            this.displayCallHistory(historyData.sessions || []);
        } catch (error) {
            console.log('No call history yet');
        }
    },

    /**
     * Load or refresh call history
     */
    async loadCallHistory() {
        if (!Auth.currentUser) return;
        
        try {
            const historyData = await API.getCallHistory(Auth.currentUser.id, 10);
            this.displayCallHistory(historyData.sessions || []);
        } catch (error) {
            console.log('Failed to load call history');
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
     * Display call history in UI
     */
    displayCallHistory(sessions) {
        if (!sessions || sessions.length === 0) {
            this.elements.callHistoryList.innerHTML = `
                <div class="call-history-empty">
                    <span class="empty-icon">📞</span>
                    <span class="empty-text">No calls yet. Start a conversation!</span>
                </div>
            `;
            return;
        }
        
        this.elements.callHistoryList.innerHTML = sessions.map(session => {
            const startedAt = new Date(session.started_at);
            const timeAgo = this.formatTimeAgo(startedAt);
            const duration = this.formatDuration(session.duration_seconds);
            const turnCount = session.turn_count || 0;
            
            // Determine call type icon
            const hasEnded = session.ended_at !== null;
            const iconClass = hasEnded ? 'outgoing' : 'missed';
            const icon = hasEnded ? '📞' : '📴';
            
            return `
                <div class="call-history-item">
                    <div class="call-item-icon ${iconClass}">
                        ${icon}
                    </div>
                    <div class="call-item-details">
                        <div class="call-item-name">
                            Synki 💕
                            ${turnCount > 0 ? `<span class="call-item-badge">${turnCount} msgs</span>` : ''}
                        </div>
                        <div class="call-item-time">${timeAgo}</div>
                    </div>
                    <div class="call-item-duration">${duration}</div>
                </div>
            `;
        }).join('');
    },

    /**
     * Format time ago (e.g., "2 hours ago", "Yesterday")
     */
    formatTimeAgo(date) {
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
        
        return date.toLocaleDateString('en-IN', { 
            day: 'numeric', 
            month: 'short' 
        });
    },

    /**
     * Format duration (e.g., "5:32", "1:02:15")
     */
    formatDuration(seconds) {
        if (!seconds || seconds === 0) return '0:00';
        
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hrs > 0) {
            return `${hrs}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins}:${secs.toString().padStart(2, '0')}`;
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
            
            // Update header call button
            this.elements.headerCallBtn.classList.add('in-call');
            this.elements.headerCallBtn.querySelector('.call-text').textContent = 'End';
            this.elements.headerCallBtn.querySelector('.call-icon').textContent = '📵';
        } else {
            this.elements.connectBtn.classList.remove('hidden');
            this.elements.disconnectBtn.classList.add('hidden');
            this.elements.micIndicator.classList.remove('active');
            this.elements.micIndicator.querySelector('.mic-text').textContent = 'Microphone Off';
            this.elements.avatarRing.classList.remove('listening', 'speaking');
            this.elements.avatarStatus.textContent = 'Ready to talk';
            
            // Update header call button
            this.elements.headerCallBtn.classList.remove('in-call');
            this.elements.headerCallBtn.querySelector('.call-text').textContent = 'Call';
            this.elements.headerCallBtn.querySelector('.call-icon').textContent = '📞';
            
            // Refresh call history after disconnecting
            this.loadCallHistory();
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
        
        this.elements.callHistoryList.innerHTML = `
            <div class="call-history-empty">
                <span class="empty-icon">📞</span>
                <span class="empty-text">No calls yet. Start a conversation!</span>
            </div>
        `;
        
        this.updateConnectionUI(false);
        this.updateStatus('default', 'Disconnected');
        this.updateEmotion('neutral');
    },

    // ============================================
    // SCHEDULE CALL METHODS
    // ============================================
    
    // Store scheduled call state
    scheduledCallTimeout: null,
    scheduledCallInterval: null,
    scheduledCallTime: null,
    scheduledCallId: null,  // Server-side call ID

    /**
     * Open the schedule call modal
     */
    openScheduleModal() {
        this.elements.scheduleModal.classList.remove('hidden');
        // Reset to default
        this.elements.quickBtns.forEach(b => b.classList.remove('selected'));
        this.elements.customMinutes.value = 10;
    },

    /**
     * Close the schedule call modal
     */
    closeScheduleModal() {
        this.elements.scheduleModal.classList.add('hidden');
    },

    /**
     * Schedule a call (server-side)
     */
    async scheduleCall() {
        const minutes = parseInt(this.elements.customMinutes.value) || 10;
        
        if (minutes < 1 || minutes > 180) {
            alert('Please enter a time between 1 and 180 minutes');
            return;
        }
        
        // Calculate scheduled time in ISO format
        const scheduledAt = new Date(Date.now() + (minutes * 60 * 1000));
        const scheduledAtISO = scheduledAt.toISOString();
        
        // Store the scheduled time locally for countdown
        this.scheduledCallTime = scheduledAt.getTime();
        
        try {
            // Save to server
            const response = await API.scheduleCall(
                Auth.currentUser.id,
                scheduledAtISO,
                `Scheduled call - ${minutes} min timer! 💕`
            );
            
            if (response.success) {
                this.scheduledCallId = response.call_id;
                
                // Store in localStorage for persistence
                localStorage.setItem('scheduledCallTime', this.scheduledCallTime.toString());
                localStorage.setItem('scheduledCallId', this.scheduledCallId);
                
                // Close modal
                this.closeScheduleModal();
                
                // Show indicator
                this.elements.scheduledIndicator.classList.remove('hidden');
                
                // Hide schedule button while scheduled
                this.elements.scheduleCallBtn.classList.add('hidden');
                
                // Start countdown display
                this.updateScheduleCountdown();
                this.scheduledCallInterval = setInterval(() => {
                    this.updateScheduleCountdown();
                }, 1000);
                
                // Set local timeout as backup (in case scheduler is slow)
                const minutes = parseInt(this.elements.customMinutes.value) || 10;
                this.scheduledCallTimeout = setTimeout(() => {
                    this.triggerScheduledCall();
                }, (minutes * 60 * 1000) + 30000); // Add 30s buffer for server
                
                // Show confirmation
                this.addMessage('system', `⏰ Synki will call you in ${minutes} minute${minutes > 1 ? 's' : ''}! 💕`);
            } else {
                this.addMessage('system', '❌ Failed to schedule call. Try again.');
            }
        } catch (error) {
            console.error('Failed to schedule call:', error);
            this.addMessage('system', '❌ Failed to schedule call. Try again.');
        }
    },

    /**
     * Update the countdown display
     */
    updateScheduleCountdown() {
        if (!this.scheduledCallTime) return;
        
        const remaining = this.scheduledCallTime - Date.now();
        
        if (remaining <= 0) {
            this.elements.scheduledCountdown.textContent = '00:00';
            return;
        }
        
        const minutes = Math.floor(remaining / 60000);
        const seconds = Math.floor((remaining % 60000) / 1000);
        
        this.elements.scheduledCountdown.textContent = 
            `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    },

    /**
     * Cancel a scheduled call
     */
    async cancelScheduledCall() {
        // Clear timeouts
        if (this.scheduledCallTimeout) {
            clearTimeout(this.scheduledCallTimeout);
            this.scheduledCallTimeout = null;
        }
        
        if (this.scheduledCallInterval) {
            clearInterval(this.scheduledCallInterval);
            this.scheduledCallInterval = null;
        }
        
        // Cancel on server if we have a call ID
        if (this.scheduledCallId && Auth.currentUser) {
            try {
                await API.cancelScheduledCall(Auth.currentUser.id, this.scheduledCallId);
            } catch (error) {
                console.error('Failed to cancel on server:', error);
            }
        }
        
        // Clear stored data
        this.scheduledCallTime = null;
        this.scheduledCallId = null;
        localStorage.removeItem('scheduledCallTime');
        localStorage.removeItem('scheduledCallId');
        
        // Hide indicator, show button
        this.elements.scheduledIndicator.classList.add('hidden');
        this.elements.scheduleCallBtn.classList.remove('hidden');
        
        this.addMessage('system', '❌ Scheduled call cancelled');
    },

    /**
     * Trigger the scheduled call
     */
    triggerScheduledCall() {
        // Clear interval
        if (this.scheduledCallInterval) {
            clearInterval(this.scheduledCallInterval);
            this.scheduledCallInterval = null;
        }
        
        // Clear stored data
        this.scheduledCallTime = null;
        this.scheduledCallId = null;
        localStorage.removeItem('scheduledCallTime');
        localStorage.removeItem('scheduledCallId');
        
        // Hide indicator, show button
        this.elements.scheduledIndicator.classList.add('hidden');
        this.elements.scheduleCallBtn.classList.remove('hidden');
        
        // Play notification sound and show notification
        this.showIncomingCallNotification();
    },

    /**
     * Show incoming call notification
     */
    showIncomingCallNotification() {
        // Try to show browser notification
        if ('Notification' in window && Notification.permission === 'granted') {
            const notification = new Notification('Synki is calling! 💕', {
                body: 'Your scheduled call is ready!',
                icon: '💕',
                tag: 'synki-call',
                requireInteraction: true
            });
            
            notification.onclick = () => {
                window.focus();
                this.handleConnect();
                notification.close();
            };
        }
        
        // Also show in-app notification
        this.addMessage('system', '📞 Synki is calling! Click "Start Talking" to answer 💕');
        
        // Highlight the connect button
        this.elements.connectBtn.classList.add('pulse-highlight');
        setTimeout(() => {
            this.elements.connectBtn.classList.remove('pulse-highlight');
        }, 5000);
        
        // Open call.html for full incoming call experience
        window.open('/call.html?message=' + encodeURIComponent('Scheduled call - Miss kar rahi thi! 💕'), 
            '_blank', 'width=400,height=600');
    },

    /**
     * Check for existing scheduled call on init
     */
    async checkExistingSchedule() {
        const storedTime = localStorage.getItem('scheduledCallTime');
        const storedCallId = localStorage.getItem('scheduledCallId');
        
        if (storedTime) {
            const scheduledTime = parseInt(storedTime);
            const now = Date.now();
            
            if (scheduledTime > now) {
                // Resume the scheduled call
                this.scheduledCallTime = scheduledTime;
                this.scheduledCallId = storedCallId;
                
                // Show indicator
                this.elements.scheduledIndicator.classList.remove('hidden');
                this.elements.scheduleCallBtn.classList.add('hidden');
                
                // Start countdown
                this.updateScheduleCountdown();
                this.scheduledCallInterval = setInterval(() => {
                    this.updateScheduleCountdown();
                }, 1000);
                
                // Set timeout for remaining time (with buffer for server)
                const remaining = scheduledTime - now;
                this.scheduledCallTimeout = setTimeout(() => {
                    this.triggerScheduledCall();
                }, remaining + 30000); // Add 30s buffer
            } else {
                // Scheduled time has passed, clear it
                localStorage.removeItem('scheduledCallTime');
                localStorage.removeItem('scheduledCallId');
            }
        }
        
        // Also check server for any pending scheduled calls
        if (Auth.currentUser) {
            try {
                const response = await API.getScheduledCalls(Auth.currentUser.id, 'pending');
                if (response.scheduled_calls && response.scheduled_calls.length > 0) {
                    // If we have a server-side scheduled call but not local, sync it
                    const serverCall = response.scheduled_calls[0];
                    const serverScheduledTime = new Date(serverCall.scheduled_at).getTime();
                    
                    if (!this.scheduledCallTime && serverScheduledTime > Date.now()) {
                        this.scheduledCallTime = serverScheduledTime;
                        this.scheduledCallId = serverCall.id;
                        
                        localStorage.setItem('scheduledCallTime', this.scheduledCallTime.toString());
                        localStorage.setItem('scheduledCallId', this.scheduledCallId);
                        
                        // Show indicator
                        this.elements.scheduledIndicator.classList.remove('hidden');
                        this.elements.scheduleCallBtn.classList.add('hidden');
                        
                        // Start countdown
                        this.updateScheduleCountdown();
                        this.scheduledCallInterval = setInterval(() => {
                            this.updateScheduleCountdown();
                        }, 1000);
                        
                        // Set timeout
                        const remaining = serverScheduledTime - Date.now();
                        this.scheduledCallTimeout = setTimeout(() => {
                            this.triggerScheduledCall();
                        }, remaining + 30000);
                    }
                }
            } catch (error) {
                console.log('Could not check server scheduled calls');
            }
        }
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
