/**
 * Synki API Service
 * Handles all HTTP requests to the backend
 */

const API = {
    /**
     * Get the stored access token
     */
    getToken() {
        return localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN);
    },

    /**
     * Make an API request
     */
    async request(endpoint, options = {}) {
        const url = `${CONFIG.API_BASE}${endpoint}`;
        const token = this.getToken();
        
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };
        
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        
        try {
            const response = await fetch(url, {
                ...options,
                headers
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || data.detail || 'Request failed');
            }
            
            return data;
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    },

    /**
     * Auth: Sign up a new user
     */
    async signup(name, email, password) {
        return this.request('/auth/signup', {
            method: 'POST',
            body: JSON.stringify({ name, email, password })
        });
    },

    /**
     * Auth: Sign in an existing user
     */
    async signin(email, password) {
        return this.request('/auth/signin', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
    },

    /**
     * Auth: Sign out
     */
    async signout() {
        try {
            await this.request('/auth/signout', { method: 'POST' });
        } catch (e) {
            // Ignore signout errors
        }
    },

    /**
     * Auth: Get current user info
     */
    async getCurrentUser() {
        return this.request('/auth/me');
    },

    /**
     * Get LiveKit token for voice connection
     */
    async getLiveKitToken(userId, roomName) {
        return this.request('/token', {
            method: 'POST',
            body: JSON.stringify({
                user_id: userId,
                room_name: roomName
            })
        });
    },

    /**
     * Get user memories
     */
    async getMemories(userId) {
        return this.request(`/memories/${userId}`);
    },

    /**
     * Get chat history
     */
    async getChatHistory(userId, limit = 20) {
        return this.request(`/chat/${userId}?limit=${limit}`);
    },

    /**
     * Save chat message
     */
    async saveChatMessage(userId, role, content, emotion = null) {
        return this.request(`/chat/${userId}`, {
            method: 'POST',
            body: JSON.stringify({ role, content, emotion })
        });
    },

    /**
     * Get call/session history
     */
    async getCallHistory(userId, limit = 20) {
        return this.request(`/sessions/${userId}?limit=${limit}`);
    },

    /**
     * Get user stats
     */
    async getUserStats(userId) {
        return this.request(`/stats/${userId}`);
    },

    // ==================== SCHEDULED CALLS ====================

    /**
     * Schedule a call
     */
    async scheduleCall(userId, scheduledAt, message = null) {
        return this.request(`/api/schedule/${userId}`, {
            method: 'POST',
            body: JSON.stringify({
                scheduled_at: scheduledAt,
                call_type: 'scheduled',
                message: message || 'Scheduled call time! 💕'
            })
        });
    },

    /**
     * Get user's scheduled calls
     */
    async getScheduledCalls(userId, status = null) {
        let url = `/api/schedule/${userId}`;
        if (status) {
            url += `?status=${status}`;
        }
        return this.request(url);
    },

    /**
     * Cancel a scheduled call
     */
    async cancelScheduledCall(userId, callId) {
        return this.request(`/api/schedule/${userId}/${callId}`, {
            method: 'DELETE'
        });
    },

    /**
     * Mark a call as answered
     */
    async markCallAnswered(callId) {
        return this.request(`/api/schedule/${callId}/answered`, {
            method: 'POST'
        });
    }
};
