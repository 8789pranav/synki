/**
 * Synki Authentication Module
 * Handles user authentication and session management
 */

const Auth = {
    currentUser: null,
    accessToken: null,

    /**
     * Initialize auth state from storage
     */
    init() {
        this.accessToken = localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN);
        const userStr = localStorage.getItem(CONFIG.STORAGE_KEYS.USER);
        
        if (userStr) {
            try {
                this.currentUser = JSON.parse(userStr);
            } catch (e) {
                this.clearSession();
            }
        }
        
        return this.isAuthenticated();
    },

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!(this.accessToken && this.currentUser);
    },

    /**
     * Save session to storage
     */
    saveSession(token, user) {
        this.accessToken = token;
        this.currentUser = user;
        
        localStorage.setItem(CONFIG.STORAGE_KEYS.TOKEN, token);
        localStorage.setItem(CONFIG.STORAGE_KEYS.USER, JSON.stringify(user));
    },

    /**
     * Clear session from storage
     */
    clearSession() {
        this.accessToken = null;
        this.currentUser = null;
        
        localStorage.removeItem(CONFIG.STORAGE_KEYS.TOKEN);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.USER);
    },

    /**
     * Sign up a new user
     */
    async signup(name, email, password) {
        const result = await API.signup(name, email, password);
        
        if (!result.success) {
            throw new Error(result.message || 'Signup failed');
        }
        
        const user = {
            id: result.user_id,
            email: email,
            name: result.name || name
        };
        
        this.saveSession(result.access_token, user);
        return user;
    },

    /**
     * Sign in an existing user
     */
    async signin(email, password) {
        const result = await API.signin(email, password);
        
        if (!result.success) {
            throw new Error(result.message || 'Login failed');
        }
        
        const user = {
            id: result.user_id,
            email: email,
            name: result.name || 'Baby'
        };
        
        this.saveSession(result.access_token, user);
        return user;
    },

    /**
     * Sign out the current user
     */
    async signout() {
        await API.signout();
        this.clearSession();
    },

    /**
     * Verify current session is valid
     */
    async verifySession() {
        if (!this.isAuthenticated()) {
            return false;
        }
        
        try {
            const userData = await API.getCurrentUser();
            
            // Update user data if needed
            this.currentUser = {
                id: userData.id,
                email: userData.email,
                name: userData.name || this.currentUser.name
            };
            
            localStorage.setItem(CONFIG.STORAGE_KEYS.USER, JSON.stringify(this.currentUser));
            return true;
        } catch (e) {
            this.clearSession();
            return false;
        }
    }
};
