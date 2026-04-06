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
    
    async def get_sessions(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get call/session history for a user."""
        if not self.is_connected:
            return []
        
        try:
            result = self.supabase.table('sessions').select(
                'id, room_name, started_at, ended_at, duration_seconds, turn_count, detected_emotions, topics_discussed'
            ).eq('user_id', user_id).order('started_at', desc=True).limit(limit).execute()
            
            if result.data:
                return result.data
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
        return []
    
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

    # ==================== SCHEDULED CALLS OPERATIONS ====================
    
    async def schedule_call(
        self, 
        user_id: str, 
        scheduled_at: str,
        call_type: str = "scheduled",
        message: str = None
    ) -> Optional[str]:
        """Schedule a call for the user."""
        if not self.is_connected:
            return None
        
        try:
            data = {
                'user_id': user_id,
                'scheduled_at': scheduled_at,
                'call_type': call_type,
                'status': 'pending'
            }
            if message:
                data['message'] = message
                
            result = self.supabase.table('scheduled_calls').insert(data).execute()
            
            if result.data:
                call_id = result.data[0]['id']
                logger.info(f"⏰ Scheduled call {call_id[:8]}... for user {user_id[:8]}... at {scheduled_at}")
                return call_id
        except Exception as e:
            logger.error(f"Error scheduling call: {e}")
        return None
    
    async def get_user_scheduled_calls(self, user_id: str, status: str = None) -> List[Dict[str, Any]]:
        """Get scheduled calls for a user."""
        if not self.is_connected:
            return []
        
        try:
            query = self.supabase.table('scheduled_calls').select('*').eq('user_id', user_id)
            
            if status:
                query = query.eq('status', status)
            
            result = query.order('scheduled_at', desc=False).execute()
            
            if result.data:
                return result.data
        except Exception as e:
            logger.error(f"Error getting scheduled calls: {e}")
        return []
    
    async def get_pending_calls_to_trigger(self) -> List[Dict[str, Any]]:
        """Get all pending calls that should be triggered now (for scheduler)."""
        if not self.is_connected:
            return []
        
        try:
            # Get calls where scheduled_at <= now and status is pending
            result = self.supabase.rpc('get_pending_calls_to_trigger').execute()
            
            if result.data:
                return result.data
        except Exception as e:
            logger.error(f"Error getting pending calls: {e}")
        return []
    
    async def update_scheduled_call_status(
        self, 
        call_id: str, 
        status: str,
        triggered_at: str = None,
        answered_at: str = None
    ) -> bool:
        """Update the status of a scheduled call."""
        if not self.is_connected:
            return False
        
        try:
            data = {'status': status}
            if triggered_at:
                data['triggered_at'] = triggered_at
            if answered_at:
                data['answered_at'] = answered_at
                
            self.supabase.table('scheduled_calls').update(data).eq('id', call_id).execute()
            logger.info(f"📞 Updated scheduled call {call_id[:8]}... to status: {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating scheduled call: {e}")
        return False
    
    async def cancel_scheduled_call(self, call_id: str, user_id: str) -> bool:
        """Cancel a scheduled call."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('scheduled_calls').update({
                'status': 'cancelled'
            }).eq('id', call_id).eq('user_id', user_id).execute()
            logger.info(f"❌ Cancelled scheduled call {call_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error cancelling scheduled call: {e}")
        return False
    
    async def delete_scheduled_call(self, call_id: str, user_id: str) -> bool:
        """Delete a scheduled call."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('scheduled_calls').delete().eq('id', call_id).eq('user_id', user_id).execute()
            logger.info(f"🗑️ Deleted scheduled call {call_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error deleting scheduled call: {e}")
        return False
    
    # ==================== PUSH TOKEN OPERATIONS ====================
    
    async def save_push_token(
        self, 
        user_id: str, 
        token: str, 
        platform: str = 'web',
        device_name: Optional[str] = None,
        browser: Optional[str] = None
    ) -> bool:
        """Save or update a push notification token."""
        if not self.is_connected:
            return False
        
        try:
            # Upsert: insert or update if exists
            data = {
                'user_id': user_id,
                'token': token,
                'platform': platform,
                'device_name': device_name,
                'browser': browser,
                'is_active': True,
                'updated_at': 'now()',
                'last_used_at': 'now()'
            }
            
            self.supabase.table('push_tokens').upsert(
                data,
                on_conflict='user_id,token'
            ).execute()
            
            logger.info(f"📱 Saved push token for user {user_id[:8]}... ({platform})")
            return True
        except Exception as e:
            logger.error(f"Error saving push token: {e}")
        return False
    
    async def get_user_push_tokens(self, user_id: str) -> list:
        """Get all active push tokens for a user."""
        if not self.is_connected:
            return []
        
        try:
            result = self.supabase.table('push_tokens').select(
                'token, platform, device_name, browser'
            ).eq('user_id', user_id).eq('is_active', True).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching push tokens: {e}")
        return []
    
    async def deactivate_push_token(self, token: str) -> bool:
        """Deactivate a push token (e.g., when it becomes invalid)."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('push_tokens').update({
                'is_active': False,
                'updated_at': 'now()'
            }).eq('token', token).execute()
            
            logger.info(f"📴 Deactivated push token {token[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Error deactivating push token: {e}")
        return False
    
    async def delete_push_token(self, user_id: str, token: str) -> bool:
        """Delete a push token."""
        if not self.is_connected:
            return False
        
        try:
            self.supabase.table('push_tokens').delete().eq(
                'user_id', user_id
            ).eq('token', token).execute()
            
            logger.info(f"🗑️ Deleted push token for user {user_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error deleting push token: {e}")
        return False

    # =========================================================================
    # LINKED USERS (Family/Care Recipients)
    # =========================================================================
    
    async def get_linked_users(self, owner_id: str) -> List[Dict[str, Any]]:
        """Get all linked users for an owner."""
        try:
            result = self.supabase.table('linked_users').select('*').eq(
                'owner_id', owner_id
            ).eq('is_active', True).order('created_at', desc=True).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting linked users: {e}")
            return []
    
    async def get_linked_user(self, linked_user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific linked user."""
        try:
            result = self.supabase.table('linked_users').select('*').eq(
                'id', linked_user_id
            ).single().execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error getting linked user: {e}")
            return None
    
    async def create_linked_user(
        self,
        owner_id: str,
        name: str,
        relationship: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        avatar_emoji: str = '👵',
        language_preference: str = 'hinglish',
        speaking_pace: str = 'normal',
        notes: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new linked user."""
        try:
            result = self.supabase.table('linked_users').insert({
                'owner_id': owner_id,
                'name': name,
                'relationship': relationship,
                'phone': phone,
                'email': email,
                'avatar_emoji': avatar_emoji,
                'language_preference': language_preference,
                'speaking_pace': speaking_pace,
                'notes': notes
            }).execute()
            
            if result.data:
                logger.info(f"👨‍👩‍👧 Created linked user {name} ({relationship}) for {owner_id[:8]}...")
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating linked user: {e}")
            return None
    
    async def update_linked_user(
        self,
        linked_user_id: str,
        **updates
    ) -> bool:
        """Update a linked user."""
        try:
            updates['updated_at'] = datetime.utcnow().isoformat()
            self.supabase.table('linked_users').update(updates).eq(
                'id', linked_user_id
            ).execute()
            
            logger.info(f"✏️ Updated linked user {linked_user_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error updating linked user: {e}")
            return False
    
    async def delete_linked_user(self, linked_user_id: str) -> bool:
        """Soft delete a linked user."""
        return await self.update_linked_user(linked_user_id, is_active=False)

    # =========================================================================
    # CALL TOPICS
    # =========================================================================
    
    async def get_call_topics(self, owner_id: str) -> List[Dict[str, Any]]:
        """Get all call topics for an owner (including presets)."""
        try:
            result = self.supabase.table('call_topics').select('*').or_(
                f'owner_id.eq.{owner_id},is_preset.eq.true'
            ).order('is_preset', desc=True).order('created_at', desc=True).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting call topics: {e}")
            return []
    
    async def get_call_topic(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific call topic."""
        try:
            result = self.supabase.table('call_topics').select('*').eq(
                'id', topic_id
            ).single().execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error getting call topic: {e}")
            return None
    
    async def create_call_topic(
        self,
        owner_id: str,
        title: str,
        description: Optional[str] = None,
        emoji: str = '💬',
        prompts: List[str] = None,
        persona_adjustments: Optional[Dict] = None,
        duration_minutes: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Create a new call topic."""
        try:
            result = self.supabase.table('call_topics').insert({
                'owner_id': owner_id,
                'title': title,
                'description': description,
                'emoji': emoji,
                'prompts': prompts or [],
                'persona_adjustments': persona_adjustments or {},
                'duration_minutes': duration_minutes
            }).execute()
            
            if result.data:
                logger.info(f"📝 Created call topic '{title}' for {owner_id[:8]}...")
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating call topic: {e}")
            return None
    
    async def create_preset_topics(self):
        """Create preset call topics (run once during setup)."""
        presets = [
            {
                'title': 'Health Check-in',
                'emoji': '🏥',
                'description': 'Check how they are feeling, any health concerns',
                'prompts': [
                    "Aaj tabiyat kaisi hai?",
                    "Dawai li aaj?",
                    "Neend achi hui kal?",
                    "Kuch dard ya takleef toh nahi?",
                    "Khana time pe kha rahe ho?"
                ],
                'duration_minutes': 5
            },
            {
                'title': 'Daily Chat',
                'emoji': '☀️',
                'description': 'General daily conversation and catching up',
                'prompts': [
                    "Aaj ka din kaisa gaya?",
                    "Kya kiya aaj?",
                    "Koi aaya milne?",
                    "TV pe kya dekha?",
                    "Bahar gaye the aaj?"
                ],
                'duration_minutes': 10
            },
            {
                'title': 'Medication Reminder',
                'emoji': '💊',
                'description': 'Remind about taking medicines',
                'prompts': [
                    "Subah ki dawai li?",
                    "Shaam ki dawai ka time ho gaya",
                    "Dawai khane ke baad kuch khaya?",
                    "Pani zyada pee rahe ho na?"
                ],
                'duration_minutes': 3
            },
            {
                'title': 'Loneliness Check',
                'emoji': '💕',
                'description': 'Companion call to reduce loneliness',
                'prompts': [
                    "Miss kar raha/rahi thi aapko",
                    "Yaad aa rahi thi aapki",
                    "Bas aise hi baat karne ka mann kiya",
                    "Aap kya kar rahe the?",
                    "Koi purani baat sunao na"
                ],
                'duration_minutes': 15
            },
            {
                'title': 'Emergency Check',
                'emoji': '🚨',
                'description': 'Quick check if everything is okay',
                'prompts': [
                    "Sab theek hai na?",
                    "Koi problem toh nahi?",
                    "Help chahiye kuch?",
                    "Main yahan hoon, batao kya hua"
                ],
                'duration_minutes': 2
            }
        ]
        
        # Note: These should be created with a system owner_id
        # For now, they'll be created per-user on first access
        return presets
    
    async def create_preset_topics_for_user(self, owner_id: str):
        """Create preset call topics for a specific user."""
        presets = await self.create_preset_topics()
        created = []
        
        for preset in presets:
            try:
                result = self.supabase.table('call_topics').insert({
                    'owner_id': owner_id,
                    'title': preset['title'],
                    'description': preset.get('description'),
                    'emoji': preset['emoji'],
                    'prompts': preset['prompts'],
                    'persona_adjustments': {},
                    'duration_minutes': preset.get('duration_minutes', 5)
                }).execute()
                
                if result.data:
                    created.append(result.data[0])
            except Exception as e:
                # Topic might already exist
                logger.debug(f"Topic creation skipped (may already exist): {e}")
        
        logger.info(f"📝 Created {len(created)} preset topics for user {owner_id[:8]}...")
        return created

    # =========================================================================
    # DELEGATED CALLS
    # =========================================================================
    
    async def get_delegated_calls(
        self,
        owner_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get delegated calls for an owner."""
        try:
            query = self.supabase.table('delegated_calls').select(
                '*, linked_users(name, relationship, avatar_emoji), call_topics(title, emoji)'
            ).eq('owner_id', owner_id)
            
            if status:
                query = query.eq('status', status)
            
            result = query.order('scheduled_at', desc=True).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting delegated calls: {e}")
            return []
    
    async def create_delegated_call(
        self,
        owner_id: str,
        linked_user_id: str,
        scheduled_at: str,
        topic_id: Optional[str] = None,
        custom_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Schedule a delegated call to a linked user."""
        try:
            result = self.supabase.table('delegated_calls').insert({
                'owner_id': owner_id,
                'linked_user_id': linked_user_id,
                'topic_id': topic_id,
                'scheduled_at': scheduled_at,
                'custom_message': custom_message,
                'status': 'pending'
            }).execute()
            
            if result.data:
                logger.info(f"📞 Scheduled delegated call for {owner_id[:8]}... at {scheduled_at}")
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error creating delegated call: {e}")
            return None
    
    async def update_delegated_call(
        self,
        call_id: str,
        **updates
    ) -> bool:
        """Update a delegated call."""
        try:
            self.supabase.table('delegated_calls').update(updates).eq(
                'id', call_id
            ).execute()
            
            logger.info(f"✏️ Updated delegated call {call_id[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Error updating delegated call: {e}")
            return False
    
    async def get_pending_delegated_calls(self) -> List[Dict[str, Any]]:
        """Get all pending delegated calls that are due (for scheduler)."""
        try:
            result = self.supabase.rpc('get_pending_delegated_calls').execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting pending delegated calls: {e}")
            return []
    
    async def complete_delegated_call(
        self,
        call_id: str,
        duration_seconds: int,
        summary: Optional[str] = None
    ) -> bool:
        """Mark a delegated call as completed with summary."""
        return await self.update_delegated_call(
            call_id,
            status='completed',
            completed_at=datetime.utcnow().isoformat(),
            call_duration_seconds=duration_seconds,
            call_summary=summary
        )


# Singleton instance
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get database service singleton."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
