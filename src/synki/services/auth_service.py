"""
Synki Authentication Service

Handles user authentication with Supabase Auth.
"""

import os
import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv('.env.local')

logger = logging.getLogger(__name__)


@dataclass
class AuthUser:
    """Authenticated user data."""
    id: str
    email: str
    name: str = "Baby"
    is_authenticated: bool = True
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


@dataclass
class AuthSession:
    """User session data."""
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None


class AuthService:
    """Service for user authentication with Supabase."""
    
    def __init__(self):
        self.supabase = None
        self.supabase_admin = None  # Service role client for admin operations
        self._sessions: Dict[str, AuthSession] = {}  # In-memory session cache
        self._initialize()
    
    def _initialize(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_KEY')  # Use anon key for auth
            service_key = os.getenv('SUPABASE_SERVICE_KEY')  # Service role for admin ops
            
            if url and key:
                self.supabase = create_client(url, key)
                logger.info("✅ Auth service initialized")
                
                # Create admin client if service key available
                if service_key:
                    self.supabase_admin = create_client(url, service_key)
                    logger.info("✅ Admin client initialized (auto-confirm enabled)")
            else:
                logger.warning("⚠️ Supabase credentials not found")
        except ImportError:
            logger.warning("⚠️ Supabase not installed")
        except Exception as e:
            logger.error(f"❌ Auth initialization failed: {e}")
    
    @property
    def is_ready(self) -> bool:
        """Check if auth service is ready."""
        return self.supabase is not None
    
    async def sign_up(self, email: str, password: str, name: str = "Baby") -> Tuple[Optional[AuthUser], Optional[str]]:
        """
        Register a new user.
        
        Returns:
            Tuple of (AuthUser, error_message)
        """
        if not self.is_ready:
            return None, "Auth service not available"
        
        try:
            # Use admin client if available (auto-confirms user)
            auth_client = self.supabase_admin if self.supabase_admin else self.supabase
            
            # Sign up with Supabase Auth
            result = auth_client.auth.admin.create_user({
                'email': email,
                'password': password,
                'email_confirm': True,  # Auto-confirm email
                'user_metadata': {
                    'name': name
                }
            }) if self.supabase_admin else self.supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'data': {
                        'name': name
                    }
                }
            })
            
            user_obj = result.user if hasattr(result, 'user') else result
            if user_obj:
                user_id = user_obj.id
                
                # Create profile in database using admin client
                db_client = self.supabase_admin if self.supabase_admin else self.supabase
                try:
                    db_client.table('profiles').insert({
                        'id': user_id,
                        'name': name,
                        'email': email
                    }).execute()
                except Exception as e:
                    logger.warning(f"Profile creation handled by trigger or already exists: {e}")
                
                # Create initial memories
                try:
                    db_client.table('memories').insert({
                        'user_id': user_id,
                        'name': name,
                        'preferences': {},
                        'facts': []
                    }).execute()
                except Exception as e:
                    logger.warning(f"Memories creation: {e}")
                
                user = AuthUser(
                    id=user_id,
                    email=email,
                    name=name,
                    created_at=datetime.utcnow()
                )
                
                logger.info(f"✅ New user registered: {email}")
                return user, None
            else:
                return None, "Registration failed"
                
        except Exception as e:
            error_msg = str(e)
            if "already registered" in error_msg.lower():
                return None, "Email already registered"
            logger.error(f"Sign up error: {e}")
            return None, str(e)
    
    async def sign_in(self, email: str, password: str) -> Tuple[Optional[AuthSession], Optional[str]]:
        """
        Sign in an existing user.
        
        Returns:
            Tuple of (AuthSession, error_message)
        """
        if not self.is_ready:
            return None, "Auth service not available"
        
        try:
            result = self.supabase.auth.sign_in_with_password({
                'email': email,
                'password': password
            })
            
            if result.user and result.session:
                session = AuthSession(
                    user_id=result.user.id,
                    access_token=result.session.access_token,
                    refresh_token=result.session.refresh_token,
                    expires_at=datetime.utcnow() + timedelta(seconds=result.session.expires_in or 3600)
                )
                
                # Cache session
                self._sessions[session.access_token] = session
                
                logger.info(f"✅ User signed in: {email}")
                return session, None
            else:
                return None, "Invalid credentials"
                
        except Exception as e:
            error_msg = str(e)
            if "invalid" in error_msg.lower():
                return None, "Invalid email or password"
            logger.error(f"Sign in error: {e}")
            return None, str(e)
    
    async def sign_out(self, access_token: str) -> bool:
        """Sign out a user."""
        if not self.is_ready:
            return False
        
        try:
            self.supabase.auth.sign_out()
            
            # Remove from cache
            if access_token in self._sessions:
                del self._sessions[access_token]
            
            logger.info("✅ User signed out")
            return True
        except Exception as e:
            logger.error(f"Sign out error: {e}")
            return False
    
    async def verify_token(self, access_token: str) -> Optional[AuthUser]:
        """
        Verify an access token and return user info.
        
        Returns:
            AuthUser if valid, None otherwise
        """
        if not self.is_ready:
            return None
        
        try:
            # Check cache first
            if access_token in self._sessions:
                session = self._sessions[access_token]
                if session.expires_at and session.expires_at > datetime.utcnow():
                    # Get user profile
                    result = self.supabase.table('profiles')\
                        .select('*')\
                        .eq('id', session.user_id)\
                        .single()\
                        .execute()
                    
                    if result.data:
                        return AuthUser(
                            id=result.data['id'],
                            email=result.data.get('email', ''),
                            name=result.data.get('name', 'Baby'),
                            is_authenticated=True
                        )
            
            # Verify with Supabase
            user = self.supabase.auth.get_user(access_token)
            if user and user.user:
                return AuthUser(
                    id=user.user.id,
                    email=user.user.email or '',
                    name=user.user.user_metadata.get('name', 'Baby'),
                    is_authenticated=True
                )
                
        except Exception as e:
            logger.error(f"Token verification error: {e}")
        
        return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[AuthUser]:
        """Get user by ID."""
        if not self.is_ready:
            return None
        
        try:
            result = self.supabase.table('profiles')\
                .select('*')\
                .eq('id', user_id)\
                .single()\
                .execute()
            
            if result.data:
                return AuthUser(
                    id=result.data['id'],
                    email=result.data.get('email', ''),
                    name=result.data.get('name', 'Baby'),
                    is_authenticated=True
                )
        except Exception as e:
            logger.error(f"Get user error: {e}")
        
        return None
    
    async def update_password(self, access_token: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """Update user password."""
        if not self.is_ready:
            return False, "Auth service not available"
        
        try:
            self.supabase.auth.update_user({
                'password': new_password
            })
            logger.info("✅ Password updated")
            return True, None
        except Exception as e:
            logger.error(f"Password update error: {e}")
            return False, str(e)
    
    async def reset_password(self, email: str) -> Tuple[bool, Optional[str]]:
        """Send password reset email."""
        if not self.is_ready:
            return False, "Auth service not available"
        
        try:
            self.supabase.auth.reset_password_email(email)
            logger.info(f"✅ Password reset email sent to {email}")
            return True, None
        except Exception as e:
            logger.error(f"Password reset error: {e}")
            return False, str(e)
    
    def generate_room_token(self, user_id: str, room_name: str) -> str:
        """Generate a token for LiveKit room access."""
        # Simple token for room identification
        data = f"{user_id}:{room_name}:{datetime.utcnow().timestamp()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


# Singleton instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get auth service singleton."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
