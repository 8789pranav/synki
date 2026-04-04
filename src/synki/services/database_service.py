"""
Synki Database Service

Handles all Supabase database operations for users, memories, chat history, and sessions.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')

logger = logging.getLogger(__name__)


@dataclass
class UserProfile:
    """User profile data."""
    id: str
    name: str = "Baby"
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class UserMemory:
    """User memory data for personalization."""
    user_id: str
    name: Optional[str] = None
    preferences: Dict[str, Any] = field(default_factory=dict)
    facts: List[str] = field(default_factory=list)
    sleep_pattern: Optional[str] = None
    common_topics: List[str] = field(default_factory=list)
    last_mood: Optional[str] = None


@dataclass
class ChatMessage:
    """Chat message data."""
    user_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    emotion: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DatabaseService:
    """Service for interacting with Supabase database."""
    
    def __init__(self):
        self.supabase = None
        self._initialize()
    
    def _initialize(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
            
            if url and key:
                self.supabase = create_client(url, key)
                logger.info("✅ Database service initialized")
            else:
                logger.warning("⚠️ Supabase credentials not found, running without persistence")
        except ImportError:
            logger.warning("⚠️ Supabase not installed, running without persistence")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self.supabase is not None
    
    # ==================== PROFILE OPERATIONS ====================
    
    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile by ID."""
        if not self.is_connected:
            return None
        
        try:
            result = self.supabase.table('profiles').select('*').eq('id', user_id).single().execute()
            if result.data:
                return UserProfile(
                    id=result.data['id'],
                    name=result.data.get('name', 'Baby'),
                    email=result.data.get('email'),
                    avatar_url=result.data.get('avatar_url'),
                    created_at=result.data.get('created_at')
                )
        except Exception as e:
            logger.error(f"Error fetching profile: {e}")
        return None
    
    async def update_profile(self, user_id: str, name: Optional[str] = None, avatar_url: Optional[str] = None) -> bool:
        """Update user profile."""
        if not self.is_connected:
            return False
        
        try:
            updates = {}
            if name:
                updates['name'] = name
            if avatar_url:
                updates['avatar_url'] = avatar_url
            
            if updates:
                self.supabase.table('profiles').update(updates).eq('id', user_id).execute()
                return True
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
        return False
    
    # ==================== MEMORY OPERATIONS ====================
    
    async def get_memories(self, user_id: str) -> Optional[UserMemory]:
        """Get user memories for personalization."""
        if not self.is_connected:
            return None
        
        try:
            result = self.supabase.table('memories').select('*').eq('user_id', user_id).single().execute()
            if result.data:
                return UserMemory(
                    user_id=result.data['user_id'],
                    name=result.data.get('name'),
                    preferences=result.data.get('preferences', {}),
                    facts=result.data.get('facts', []),
                    sleep_pattern=result.data.get('sleep_pattern'),
                    common_topics=result.data.get('common_topics', []),
                    last_mood=result.data.get('last_mood')
                )
        except Exception as e:
            # No memories yet is fine
            if 'No rows' not in str(e):
                logger.error(f"Error fetching memories: {e}")
        return None
    
    async def save_memories(self, memory: UserMemory) -> bool:
        """Save or update user memories."""
        if not self.is_connected:
            return False
        
        try:
            data = {
                'user_id': memory.user_id,
                'name': memory.name,
                'preferences': memory.preferences,
                'facts': memory.facts,
                'sleep_pattern': memory.sleep_pattern,
                'common_topics': memory.common_topics,
                'last_mood': memory.last_mood
            }
            
            # Upsert (insert or update)
            self.supabase.table('memories').upsert(data, on_conflict='user_id').execute()
            logger.info(f"💾 Saved memories for user {memory.user_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error saving memories: {e}")
        return False
    
    async def add_fact(self, user_id: str, fact: str) -> bool:
        """Add a new fact to user's memory."""
        memory = await self.get_memories(user_id)
        if memory:
            if fact not in memory.facts:
                memory.facts.append(fact)
                # Keep only last 50 facts
                memory.facts = memory.facts[-50:]
                return await self.save_memories(memory)
        else:
            # Create new memory with fact
            memory = UserMemory(user_id=user_id, facts=[fact])
            return await self.save_memories(memory)
        return False
    
    async def update_mood(self, user_id: str, mood: str) -> bool:
        """Update user's last detected mood."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('memories').upsert({
                'user_id': user_id,
                'last_mood': mood
            }, on_conflict='user_id').execute()
            return True
        except Exception as e:
            logger.error(f"Error updating mood: {e}")
        return False
    
    # ==================== CHAT HISTORY OPERATIONS ====================
    
    async def save_chat_message(self, message: ChatMessage) -> bool:
        """Save a chat message to history."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('chat_history').insert({
                'user_id': message.user_id,
                'role': message.role,
                'content': message.content,
                'emotion': message.emotion,
                'metadata': message.metadata
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
        return False
    
    async def get_recent_chat(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent chat messages for context."""
        if not self.is_connected:
            return []
        
        try:
            result = self.supabase.table('chat_history')\
                .select('role, content, emotion, created_at')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            # Return in chronological order
            return list(reversed(result.data)) if result.data else []
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
        return []
    
    # ==================== SESSION OPERATIONS ====================
    
    async def start_session(self, user_id: str, room_name: str) -> Optional[str]:
        """Start a new voice session."""
        if not self.is_connected:
            return None
        
        try:
            result = self.supabase.table('sessions').insert({
                'user_id': user_id,
                'room_name': room_name,
                'started_at': datetime.utcnow().isoformat()
            }).execute()
            
            if result.data:
                session_id = result.data[0]['id']
                logger.info(f"🎙️ Started session {session_id[:8]}... for user {user_id[:8]}...")
                return session_id
        except Exception as e:
            logger.error(f"Error starting session: {e}")
        return None
    
    async def end_session(
        self, 
        session_id: str, 
        turn_count: int = 0,
        emotions: List[str] = None,
        topics: List[str] = None
    ) -> bool:
        """End a voice session with summary data."""
        if not self.is_connected:
            return False
        
        try:
            # Calculate duration
            result = self.supabase.table('sessions').select('started_at').eq('id', session_id).single().execute()
            if result.data:
                started = datetime.fromisoformat(result.data['started_at'].replace('Z', '+00:00'))
                duration = int((datetime.utcnow().replace(tzinfo=started.tzinfo) - started).total_seconds())
                
                self.supabase.table('sessions').update({
                    'ended_at': datetime.utcnow().isoformat(),
                    'duration_seconds': duration,
                    'turn_count': turn_count,
                    'detected_emotions': emotions or [],
                    'topics_discussed': topics or []
                }).eq('id', session_id).execute()
                
                logger.info(f"📊 Session ended: {duration}s, {turn_count} turns")
                return True
        except Exception as e:
            logger.error(f"Error ending session: {e}")
        return False
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user conversation statistics."""
        if not self.is_connected:
            return {}
        
        try:
            # Get from database function
            result = self.supabase.rpc('get_conversation_summary', {'p_user_id': user_id}).execute()
            if result.data:
                return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Error fetching user stats: {e}")
        return {}


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
