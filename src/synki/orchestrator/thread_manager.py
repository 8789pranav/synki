"""
Thread Manager

Manages conversation threads - topical discussions that span
multiple turns and potentially multiple sessions.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog

from .layered_memory import (
    ConversationThread,
    ThreadType,
    Entity,
    EntityType,
)

logger = structlog.get_logger(__name__)


class ThreadManager:
    """
    Manages conversation threads for multi-turn topical discussions.
    
    A thread represents a discussion about a specific topic that may:
    - Span multiple turns in a single session
    - Span multiple sessions (e.g., ongoing movie discussion)
    - Have associated entities (the movie, person, etc.)
    - Have pending follow-ups
    """
    
    # Thread type detection patterns
    THREAD_PATTERNS = {
        ThreadType.MOVIE_DISCUSSION: [
            "movie", "film", "देखी", "dekhi", "watched", "watching",
            "show", "series", "web series", "webseries", "netflix", "prime"
        ],
        ThreadType.WORK_STRESS: [
            "work", "office", "boss", "job", "meeting", "deadline",
            "काम", "kaam", "naukri", "tension", "stress"
        ],
        ThreadType.SKINCARE: [
            "skin", "face", "acne", "pimple", "cream", "routine",
            "skincare", "sunscreen", "moisturizer"
        ],
        ThreadType.HEALTH: [
            "health", "medicine", "doctor", "dawai", "tablet",
            "sick", "bimar", "pain", "dard", "fever", "bukhar"
        ],
        ThreadType.RELATIONSHIP: [
            "boyfriend", "girlfriend", "bf", "gf", "partner",
            "relationship", "dating", "married", "shaadi"
        ],
        ThreadType.HOBBY: [
            "hobby", "hobbies", "pastime", "game", "gaming",
            "music", "reading", "writing", "art", "craft"
        ],
        ThreadType.RECOMMENDATION: [
            "suggest", "recommend", "batao", "kya dekhun",
            "what should", "best", "top", "favorite"
        ],
    }
    
    # Thread expiry times
    THREAD_EXPIRY = {
        ThreadType.MOVIE_DISCUSSION: timedelta(days=7),
        ThreadType.WORK_STRESS: timedelta(days=3),
        ThreadType.SKINCARE: timedelta(days=14),
        ThreadType.HEALTH: timedelta(days=7),
        ThreadType.RELATIONSHIP: timedelta(days=7),
        ThreadType.HOBBY: timedelta(days=14),
        ThreadType.RECOMMENDATION: timedelta(days=3),
        ThreadType.GENERAL: timedelta(days=3),
    }
    
    def __init__(self, supabase_client: Any | None = None):
        """Initialize thread manager."""
        self._supabase = supabase_client
        self._active_threads: dict[str, ConversationThread] = {}
        
        logger.info("thread_manager_initialized")
    
    async def detect_thread_type(
        self,
        message: str,
        entities: list[Entity] | None = None
    ) -> ThreadType | None:
        """
        Detect if message starts or continues a thread.
        
        Returns ThreadType if thread detected, None otherwise.
        """
        message_lower = message.lower()
        
        # Score each thread type
        scores = {}
        for thread_type, keywords in self.THREAD_PATTERNS.items():
            score = sum(1 for kw in keywords if kw in message_lower)
            if score > 0:
                scores[thread_type] = score
        
        # Boost based on entities
        if entities:
            for entity in entities:
                if entity.type == EntityType.MOVIE:
                    scores[ThreadType.MOVIE_DISCUSSION] = scores.get(ThreadType.MOVIE_DISCUSSION, 0) + 2
                elif entity.type == EntityType.MEDICINE:
                    scores[ThreadType.HEALTH] = scores.get(ThreadType.HEALTH, 0) + 2
                elif entity.type == EntityType.ACTIVITY:
                    scores[ThreadType.HOBBY] = scores.get(ThreadType.HOBBY, 0) + 2
        
        if not scores:
            return None
        
        # Return highest scoring type
        best_type = max(scores, key=scores.get)
        if scores[best_type] >= 1:
            return best_type
        
        return None
    
    async def get_or_create_thread(
        self,
        user_id: str,
        thread_type: ThreadType,
        title: str,
        entities: list[Entity] | None = None
    ) -> ConversationThread:
        """
        Get existing active thread of type or create new one.
        
        Reuses existing threads if they match type and aren't expired.
        """
        # Check for existing active thread of this type
        existing = await self.get_active_thread_by_type(user_id, thread_type)
        
        if existing and not self._is_thread_expired(existing):
            # Update with new entities if provided
            if entities:
                existing.entities.extend(entities)
            existing.last_message_at = datetime.now()
            await self._save_thread(existing)
            return existing
        
        # Create new thread
        expiry = datetime.now() + self.THREAD_EXPIRY.get(thread_type, timedelta(days=3))
        
        thread = ConversationThread(
            id=str(uuid.uuid4()),
            user_id=user_id,
            thread_type=thread_type,
            title=title,
            entities=entities or [],
            expires_at=expiry
        )
        
        await self._save_thread(thread)
        self._active_threads[thread.id] = thread
        
        logger.info(
            "thread_created",
            thread_id=thread.id,
            thread_type=thread_type.value,
            title=title
        )
        
        return thread
    
    async def get_active_thread_by_type(
        self,
        user_id: str,
        thread_type: ThreadType
    ) -> ConversationThread | None:
        """Get active thread of specific type for user."""
        # Check cache first
        for thread in self._active_threads.values():
            if (thread.user_id == user_id and 
                thread.thread_type == thread_type and 
                thread.status == "active"):
                return thread
        
        # Query database
        if self._supabase:
            try:
                result = await self._supabase.table("conversation_threads").select("*").eq(
                    "user_id", user_id
                ).eq("thread_type", thread_type.value).eq(
                    "status", "active"
                ).order("last_message_at", desc=True).limit(1).execute()
                
                if result.data:
                    thread = self._dict_to_thread(result.data[0])
                    self._active_threads[thread.id] = thread
                    return thread
            except Exception as e:
                logger.error("thread_fetch_failed", error=str(e))
        
        return None
    
    async def get_all_active_threads(self, user_id: str) -> list[ConversationThread]:
        """Get all active threads for user."""
        threads = []
        
        if self._supabase:
            try:
                result = await self._supabase.table("conversation_threads").select("*").eq(
                    "user_id", user_id
                ).eq("status", "active").order(
                    "last_message_at", desc=True
                ).execute()
                
                for row in result.data:
                    thread = self._dict_to_thread(row)
                    if not self._is_thread_expired(thread):
                        threads.append(thread)
                        self._active_threads[thread.id] = thread
                    else:
                        # Mark expired thread as inactive
                        await self._close_thread(thread.id, "expired")
            except Exception as e:
                logger.error("threads_fetch_failed", error=str(e))
        
        return threads
    
    async def update_thread_summary(self, thread_id: str, summary: str):
        """Update thread with new summary."""
        if self._supabase:
            try:
                await self._supabase.table("conversation_threads").update({
                    "summary": summary,
                    "last_message_at": datetime.now().isoformat()
                }).eq("id", thread_id).execute()
                
                if thread_id in self._active_threads:
                    self._active_threads[thread_id].summary = summary
                    self._active_threads[thread_id].last_message_at = datetime.now()
            except Exception as e:
                logger.error("thread_summary_update_failed", error=str(e))
    
    async def set_pending_followup(self, thread_id: str, followup: str | None):
        """Set or clear pending follow-up for thread."""
        if self._supabase:
            try:
                await self._supabase.table("conversation_threads").update({
                    "pending_followup": followup
                }).eq("id", thread_id).execute()
                
                if thread_id in self._active_threads:
                    self._active_threads[thread_id].pending_followup = followup
            except Exception as e:
                logger.error("thread_followup_update_failed", error=str(e))
    
    async def add_entity_to_thread(self, thread_id: str, entity: Entity):
        """Add entity to thread."""
        if thread_id in self._active_threads:
            self._active_threads[thread_id].entities.append(entity)
        
        if self._supabase:
            try:
                thread = self._active_threads.get(thread_id)
                user_id = thread.user_id if thread else None
                
                if user_id:
                    await self._supabase.table("thread_entities").insert({
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "entity_type": entity.type.value,
                        "entity_value": entity.value,
                        "confidence": entity.confidence,
                        "mentioned_at": entity.mentioned_at.isoformat()
                    }).execute()
            except Exception as e:
                logger.error("entity_add_failed", error=str(e))
    
    async def close_thread(self, thread_id: str, reason: str = "completed"):
        """Close/complete a thread."""
        await self._close_thread(thread_id, reason)
    
    async def get_pending_followups(self, user_id: str) -> list[dict]:
        """Get all pending follow-ups for user across threads."""
        followups = []
        
        threads = await self.get_all_active_threads(user_id)
        for thread in threads:
            if thread.pending_followup:
                followups.append({
                    "thread_id": thread.id,
                    "thread_type": thread.thread_type.value,
                    "title": thread.title,
                    "followup": thread.pending_followup,
                    "entities": thread.entities
                })
        
        return followups
    
    def generate_thread_context(self, threads: list[ConversationThread]) -> str:
        """
        Generate context string from active threads for LLM prompt.
        """
        if not threads:
            return ""
        
        context_parts = ["Active conversation threads:"]
        
        for thread in threads[:5]:  # Limit to 5 threads
            entity_str = ", ".join([
                f"{e.type.value}: {e.value}" for e in thread.entities[:3]
            ]) if thread.entities else "none"
            
            context_parts.append(
                f"- {thread.thread_type.value}: {thread.title}"
                f"\n  Summary: {thread.summary or 'ongoing'}"
                f"\n  Key items: {entity_str}"
                f"{f'\n  Pending: {thread.pending_followup}' if thread.pending_followup else ''}"
            )
        
        return "\n".join(context_parts)
    
    async def detect_thread_continuation(
        self,
        message: str,
        user_id: str,
        entities: list[Entity] | None = None
    ) -> ConversationThread | None:
        """
        Detect if message continues an existing thread.
        
        Looks for:
        - Reference to thread entities
        - Same topic as recent thread
        - Response to pending follow-up
        """
        active_threads = await self.get_all_active_threads(user_id)
        
        if not active_threads:
            return None
        
        message_lower = message.lower()
        
        # Check if message contains thread entities
        for thread in active_threads:
            for entity in thread.entities:
                if entity.value.lower() in message_lower:
                    return thread
        
        # Check if incoming entities match thread entities
        if entities:
            for thread in active_threads:
                for new_entity in entities:
                    for thread_entity in thread.entities:
                        if (new_entity.type == thread_entity.type and
                            new_entity.value.lower() == thread_entity.value.lower()):
                            return thread
        
        # Check for reference words that suggest continuation
        continuation_patterns = [
            r"(?:that|वो|wo|woh)\s+(?:movie|film|show)",
            r"(?:usme|uski|uska|its|their)\b",
            r"(?:haan|yes|yeah|ha|ya)\s+(?:wo|that|वो)",
            r"(?:aur|and|also)\s+(?:kya|what)\s+(?:hua|happened)",
        ]
        
        for pattern in continuation_patterns:
            import re
            if re.search(pattern, message, re.IGNORECASE):
                # Return most recent thread
                if active_threads:
                    return active_threads[0]
        
        return None
    
    # =========================================================================
    # PRIVATE METHODS
    # =========================================================================
    
    async def _save_thread(self, thread: ConversationThread):
        """Save thread to database."""
        if self._supabase:
            try:
                await self._supabase.table("conversation_threads").upsert({
                    "id": thread.id,
                    "user_id": thread.user_id,
                    "thread_type": thread.thread_type.value,
                    "title": thread.title,
                    "status": thread.status,
                    "summary": thread.summary,
                    "pending_followup": thread.pending_followup,
                    "expires_at": thread.expires_at.isoformat(),
                    "started_at": thread.started_at.isoformat(),
                    "last_message_at": thread.last_message_at.isoformat()
                }).execute()
            except Exception as e:
                logger.error("thread_save_failed", error=str(e))
    
    async def _close_thread(self, thread_id: str, reason: str):
        """Close a thread."""
        if self._supabase:
            try:
                await self._supabase.table("conversation_threads").update({
                    "status": reason
                }).eq("id", thread_id).execute()
            except Exception as e:
                logger.error("thread_close_failed", error=str(e))
        
        if thread_id in self._active_threads:
            del self._active_threads[thread_id]
        
        logger.info("thread_closed", thread_id=thread_id, reason=reason)
    
    def _is_thread_expired(self, thread: ConversationThread) -> bool:
        """Check if thread has expired."""
        return datetime.now() > thread.expires_at
    
    def _dict_to_thread(self, data: dict) -> ConversationThread:
        """Convert database row to ConversationThread."""
        return ConversationThread(
            id=data["id"],
            user_id=data["user_id"],
            thread_type=ThreadType(data["thread_type"]),
            title=data["title"],
            status=data.get("status", "active"),
            summary=data.get("summary", ""),
            pending_followup=data.get("pending_followup"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(),
            last_message_at=datetime.fromisoformat(data["last_message_at"]) if data.get("last_message_at") else datetime.now(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else datetime.now() + timedelta(days=7)
        )
