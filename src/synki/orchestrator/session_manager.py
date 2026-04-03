"""
Session Manager

Manages user sessions, state persistence, and session lifecycle.
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from ..models import (
    ContextPacket,
    PersonaProfile,
    SessionState,
)

logger = structlog.get_logger(__name__)


class SessionManager:
    """Manages user sessions and their state."""
    
    def __init__(self, redis_client: Any | None = None):
        """
        Initialize session manager.
        
        Args:
            redis_client: Optional Redis client for persistence
        """
        self._sessions: dict[str, SessionState] = {}
        self._redis = redis_client
        self._lock = asyncio.Lock()
    
    async def create_session(
        self,
        user_id: str,
        room_name: str,
        persona: PersonaProfile | None = None,
    ) -> SessionState:
        """
        Create a new session.
        
        Args:
            user_id: User identifier
            room_name: LiveKit room name
            persona: Optional persona profile
            
        Returns:
            New SessionState instance
        """
        session_id = f"session_{uuid4().hex[:12]}"
        
        session = SessionState(
            session_id=session_id,
            user_id=user_id,
            room_name=room_name,
            persona=persona or PersonaProfile(),
            context=ContextPacket(),
        )
        
        async with self._lock:
            self._sessions[session_id] = session
        
        # Persist to Redis if available
        if self._redis:
            await self._persist_session(session)
        
        logger.info(
            "session_created",
            session_id=session_id,
            user_id=user_id,
            room_name=room_name,
        )
        
        return session
    
    async def get_session(self, session_id: str) -> SessionState | None:
        """
        Get session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionState if found, None otherwise
        """
        # Check memory cache first
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        # Try Redis if available
        if self._redis:
            session = await self._load_session(session_id)
            if session:
                self._sessions[session_id] = session
                return session
        
        return None
    
    async def get_session_by_room(self, room_name: str) -> SessionState | None:
        """
        Get session by room name.
        
        Args:
            room_name: LiveKit room name
            
        Returns:
            SessionState if found, None otherwise
        """
        for session in self._sessions.values():
            if session.room_name == room_name:
                return session
        return None
    
    async def update_session(
        self,
        session_id: str,
        **updates: Any,
    ) -> SessionState | None:
        """
        Update session state.
        
        Args:
            session_id: Session identifier
            **updates: Fields to update
            
        Returns:
            Updated SessionState if found
        """
        session = await self.get_session(session_id)
        if not session:
            return None
        
        # Update fields
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)
        
        session.last_activity = datetime.now()
        
        # Persist
        if self._redis:
            await self._persist_session(session)
        
        return session
    
    async def update_context(
        self,
        session_id: str,
        user_message: str | None = None,
        assistant_message: str | None = None,
    ) -> SessionState | None:
        """
        Update session context with new messages.
        
        Args:
            session_id: Session identifier
            user_message: New user message
            assistant_message: New assistant message
            
        Returns:
            Updated SessionState if found
        """
        session = await self.get_session(session_id)
        if not session:
            return None
        
        if user_message:
            session.context.recent_user_messages.append(user_message)
            # Keep only last 5 messages
            session.context.recent_user_messages = \
                session.context.recent_user_messages[-5:]
        
        if assistant_message:
            session.context.recent_assistant_messages.append(assistant_message)
            session.context.recent_assistant_messages = \
                session.context.recent_assistant_messages[-5:]
            # Track recent phrases for anti-repetition
            session.recent_phrases.append(assistant_message[:50])
            session.recent_phrases = session.recent_phrases[-10:]
        
        session.context.turn_count += 1
        session.turn_count += 1
        session.last_activity = datetime.now()
        
        # Update session duration
        duration = (datetime.now() - session.started_at).total_seconds() * 1000
        session.context.session_duration_ms = int(duration)
        
        if self._redis:
            await self._persist_session(session)
        
        return session
    
    async def end_session(self, session_id: str) -> bool:
        """
        End and cleanup a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if session was ended
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                
                # Remove from Redis
                if self._redis:
                    await self._redis.delete(f"session:{session_id}")
                
                logger.info("session_ended", session_id=session_id)
                return True
        
        return False
    
    async def _persist_session(self, session: SessionState) -> None:
        """Persist session to Redis."""
        if not self._redis:
            return
        
        try:
            key = f"session:{session.session_id}"
            data = session.model_dump_json()
            await self._redis.setex(key, 3600, data)  # 1 hour TTL
        except Exception as e:
            logger.error("session_persist_failed", error=str(e))
    
    async def _load_session(self, session_id: str) -> SessionState | None:
        """Load session from Redis."""
        if not self._redis:
            return None
        
        try:
            key = f"session:{session_id}"
            data = await self._redis.get(key)
            if data:
                return SessionState.model_validate_json(data)
        except Exception as e:
            logger.error("session_load_failed", error=str(e))
        
        return None
