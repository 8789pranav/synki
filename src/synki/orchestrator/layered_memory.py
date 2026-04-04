"""
Layered Memory Service

Implements the 6-layer memory architecture:
- L0: Realtime turn buffer (in-process)
- L1: Short-term session memory (Redis, 3-day TTL)
- L2: Thread memory (PostgreSQL)
- L3: Long-term profile memory (PostgreSQL)
- L4: Semantic recall (pgvector embeddings)
- L5: Anti-repetition memory (Redis + PostgreSQL)
- L6: Summaries and event memory (PostgreSQL)
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class MemoryCategory(str, Enum):
    """Categories for memory facts."""
    PREFERENCE = "preference"
    HABIT = "habit"
    PERSONAL = "personal"
    MEDICAL = "medical"
    HOBBY = "hobby"
    WORK = "work"
    RELATIONSHIP = "relationship"


class ThreadType(str, Enum):
    """Types of conversation threads."""
    MOVIE_DISCUSSION = "movie_discussion"
    WORK_STRESS = "work_stress"
    SKINCARE = "skincare"
    HEALTH = "health"
    RELATIONSHIP = "relationship"
    HOBBY = "hobby"
    GENERAL = "general"
    RECOMMENDATION = "recommendation"


class EntityType(str, Enum):
    """Types of entities that can be extracted."""
    MOVIE = "movie"
    PERSON = "person"
    PLACE = "place"
    PRODUCT = "product"
    TIME = "time"
    MEDICINE = "medicine"
    FOOD = "food"
    ACTIVITY = "activity"


@dataclass
class Entity:
    """Extracted entity from conversation."""
    type: EntityType
    value: str
    confidence: float = 0.8
    metadata: dict = field(default_factory=dict)
    mentioned_at: datetime = field(default_factory=datetime.now)


@dataclass
class ConversationThread:
    """Active conversation thread."""
    id: str
    user_id: str
    thread_type: ThreadType
    title: str
    status: str = "active"
    summary: str = ""
    entities: list[Entity] = field(default_factory=list)
    pending_followup: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    last_message_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(days=7))


@dataclass
class MemoryFact:
    """A durable memory fact about the user."""
    category: MemoryCategory
    fact_key: str
    fact_value: str
    confidence: float = 0.7
    source: str = "conversation"
    mention_count: int = 1
    first_mentioned_at: datetime = field(default_factory=datetime.now)
    last_mentioned_at: datetime = field(default_factory=datetime.now)


@dataclass
class TurnBuffer:
    """L0: Realtime turn buffer for current conversation."""
    user_transcript_fragments: list[str] = field(default_factory=list)
    user_current_turn: str = ""
    bot_current_turn: str = ""
    is_interrupted: bool = False
    turn_start_time: datetime = field(default_factory=datetime.now)
    
    def add_fragment(self, fragment: str):
        """Add a transcript fragment."""
        self.user_transcript_fragments.append(fragment)
        self.user_current_turn = " ".join(self.user_transcript_fragments)
    
    def clear(self):
        """Clear the buffer for next turn."""
        self.user_transcript_fragments = []
        self.user_current_turn = ""
        self.bot_current_turn = ""
        self.is_interrupted = False
        self.turn_start_time = datetime.now()


@dataclass
class SessionState:
    """L1: Short-term session state."""
    user_id: str
    session_id: str
    
    # Recent messages (last 20-50 turns)
    recent_messages: list[dict] = field(default_factory=list)
    
    # Current state
    active_topic: str | None = None
    current_emotional_state: str = "neutral"
    pending_followup: str | None = None
    
    # Active entities (things mentioned in this session)
    active_entities: dict[str, Entity] = field(default_factory=dict)
    
    # Active thread IDs
    active_thread_ids: list[str] = field(default_factory=list)
    
    # Anti-repetition tracking
    recent_openers: list[str] = field(default_factory=list)
    recent_patterns: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    last_activity_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str, emotion: str | None = None):
        """Add a message to recent history."""
        self.recent_messages.append({
            "role": role,
            "content": content,
            "emotion": emotion,
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 50 messages
        if len(self.recent_messages) > 50:
            self.recent_messages = self.recent_messages[-50:]
        self.last_activity_at = datetime.now()
    
    def add_entity(self, entity: Entity):
        """Track an active entity."""
        key = f"{entity.type.value}:{entity.value.lower()}"
        self.active_entities[key] = entity
    
    def get_entity(self, entity_type: EntityType) -> Entity | None:
        """Get the most recent entity of a type."""
        for key, entity in sorted(
            self.active_entities.items(),
            key=lambda x: x[1].mentioned_at,
            reverse=True
        ):
            if entity.type == entity_type:
                return entity
        return None
    
    def add_opener(self, opener: str):
        """Track used opener for anti-repetition."""
        self.recent_openers.append(opener)
        if len(self.recent_openers) > 20:
            self.recent_openers = self.recent_openers[-20:]
    
    def is_opener_recent(self, opener: str) -> bool:
        """Check if opener was recently used."""
        return opener.lower().strip() in [o.lower().strip() for o in self.recent_openers[-5:]]


class LayeredMemoryService:
    """
    Comprehensive layered memory service.
    
    Implements intelligent memory retrieval order:
    1. Current turn buffer (L0)
    2. Short-term session state (L1)
    3. Active thread memory (L2)
    4. Recent entity memory
    5. Long-term profile (L3)
    6. Semantic recall (L4)
    7. Anti-repetition check (L5)
    """
    
    def __init__(
        self,
        redis_client: Any | None = None,
        supabase_client: Any | None = None,
        openai_client: Any | None = None,
    ):
        """
        Initialize the layered memory service.
        
        Args:
            redis_client: Redis client for L0/L1/L5
            supabase_client: Supabase client for L2/L3/L4/L6
            openai_client: OpenAI client for embeddings
        """
        self._redis = redis_client
        self._supabase = supabase_client
        self._openai = openai_client
        
        # In-memory caches
        self._turn_buffers: dict[str, TurnBuffer] = {}
        self._session_states: dict[str, SessionState] = {}
        self._thread_cache: dict[str, ConversationThread] = {}
        self._profile_cache: dict[str, dict] = {}
        
        # TTL settings
        self.session_ttl = 3 * 24 * 60 * 60  # 3 days in seconds
        self.thread_ttl = 7 * 24 * 60 * 60   # 7 days in seconds
        
        logger.info("layered_memory_service_initialized")
    
    # =========================================================================
    # L0: REALTIME TURN BUFFER
    # =========================================================================
    
    def get_turn_buffer(self, session_id: str) -> TurnBuffer:
        """Get or create turn buffer for session."""
        if session_id not in self._turn_buffers:
            self._turn_buffers[session_id] = TurnBuffer()
        return self._turn_buffers[session_id]
    
    def add_transcript_fragment(self, session_id: str, fragment: str):
        """Add a transcript fragment to the turn buffer."""
        buffer = self.get_turn_buffer(session_id)
        buffer.add_fragment(fragment)
    
    def finalize_user_turn(self, session_id: str) -> str:
        """Finalize user turn and return complete transcript."""
        buffer = self.get_turn_buffer(session_id)
        complete = buffer.user_current_turn
        return complete
    
    def set_bot_turn(self, session_id: str, response: str):
        """Set the bot's response for current turn."""
        buffer = self.get_turn_buffer(session_id)
        buffer.bot_current_turn = response
    
    def clear_turn_buffer(self, session_id: str):
        """Clear turn buffer after turn is complete."""
        if session_id in self._turn_buffers:
            self._turn_buffers[session_id].clear()
    
    # =========================================================================
    # L1: SHORT-TERM SESSION MEMORY
    # =========================================================================
    
    async def get_session_state(self, user_id: str, session_id: str) -> SessionState:
        """Get or create session state."""
        cache_key = f"{user_id}:{session_id}"
        
        # Check memory cache
        if cache_key in self._session_states:
            return self._session_states[cache_key]
        
        # Try Redis
        if self._redis:
            try:
                redis_key = f"session:{user_id}:{session_id}:state"
                data = await self._redis.get(redis_key)
                if data:
                    state_dict = json.loads(data)
                    state = self._dict_to_session_state(state_dict)
                    self._session_states[cache_key] = state
                    return state
            except Exception as e:
                logger.error("redis_session_load_failed", error=str(e))
        
        # Create new session state
        state = SessionState(user_id=user_id, session_id=session_id)
        self._session_states[cache_key] = state
        return state
    
    async def save_session_state(self, state: SessionState):
        """Save session state to Redis."""
        cache_key = f"{state.user_id}:{state.session_id}"
        self._session_states[cache_key] = state
        
        if self._redis:
            try:
                redis_key = f"session:{state.user_id}:{state.session_id}:state"
                data = self._session_state_to_dict(state)
                await self._redis.setex(redis_key, self.session_ttl, json.dumps(data))
            except Exception as e:
                logger.error("redis_session_save_failed", error=str(e))
    
    async def add_message_to_session(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        emotion: str | None = None
    ):
        """Add a message to session history."""
        state = await self.get_session_state(user_id, session_id)
        state.add_message(role, content, emotion)
        await self.save_session_state(state)
    
    async def update_session_topic(self, user_id: str, session_id: str, topic: str):
        """Update the active topic for session."""
        state = await self.get_session_state(user_id, session_id)
        state.active_topic = topic
        state.recent_topics.append(topic)
        if len(state.recent_topics) > 10:
            state.recent_topics = state.recent_topics[-10:]
        await self.save_session_state(state)
    
    async def update_session_emotion(self, user_id: str, session_id: str, emotion: str):
        """Update current emotional state."""
        state = await self.get_session_state(user_id, session_id)
        state.current_emotional_state = emotion
        await self.save_session_state(state)
    
    async def add_entity_to_session(self, user_id: str, session_id: str, entity: Entity):
        """Add an entity to session tracking."""
        state = await self.get_session_state(user_id, session_id)
        state.add_entity(entity)
        await self.save_session_state(state)
    
    # =========================================================================
    # L2: THREAD MEMORY
    # =========================================================================
    
    async def create_thread(
        self,
        user_id: str,
        thread_type: ThreadType,
        title: str,
        initial_entities: list[Entity] | None = None
    ) -> ConversationThread:
        """Create a new conversation thread."""
        import uuid
        
        thread = ConversationThread(
            id=str(uuid.uuid4()),
            user_id=user_id,
            thread_type=thread_type,
            title=title,
            entities=initial_entities or []
        )
        
        # Save to database
        if self._supabase:
            try:
                await self._supabase.table("conversation_threads").insert({
                    "id": thread.id,
                    "user_id": user_id,
                    "thread_type": thread_type.value,
                    "title": title,
                    "status": "active",
                    "entities": [self._entity_to_dict(e) for e in thread.entities],
                    "expires_at": thread.expires_at.isoformat()
                }).execute()
                
                # Save entities
                for entity in thread.entities:
                    await self._supabase.table("thread_entities").insert({
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "entity_type": entity.type.value,
                        "entity_value": entity.value,
                        "confidence": entity.confidence,
                        "mentioned_at": entity.mentioned_at.isoformat()
                    }).execute()
                    
            except Exception as e:
                logger.error("thread_create_failed", error=str(e))
        
        # Cache
        self._thread_cache[thread.id] = thread
        
        logger.info(
            "thread_created",
            thread_id=thread.id,
            thread_type=thread_type.value,
            title=title
        )
        
        return thread
    
    async def get_active_threads(self, user_id: str) -> list[ConversationThread]:
        """Get all active threads for user."""
        threads = []
        
        if self._supabase:
            try:
                result = await self._supabase.table("conversation_threads").select("*").eq(
                    "user_id", user_id
                ).eq("status", "active").execute()
                
                for row in result.data:
                    thread = self._dict_to_thread(row)
                    threads.append(thread)
                    self._thread_cache[thread.id] = thread
                    
            except Exception as e:
                logger.error("threads_fetch_failed", error=str(e))
        
        return threads
    
    async def resolve_entity_reference(
        self,
        user_id: str,
        entity_type: EntityType,
        session_id: str | None = None,
        hours_back: int = 24
    ) -> Entity | None:
        """
        Resolve a vague entity reference like "that movie".
        
        Checks in order:
        1. Session entities (L1)
        2. Active thread entities (L2)
        3. Database (PostgreSQL)
        """
        # Check session first
        if session_id:
            state = await self.get_session_state(user_id, session_id)
            entity = state.get_entity(entity_type)
            if entity:
                return entity
        
        # Check active threads
        threads = await self.get_active_threads(user_id)
        for thread in threads:
            for entity in thread.entities:
                if entity.type == entity_type:
                    return entity
        
        # Check database
        if self._supabase:
            try:
                cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
                result = await self._supabase.table("thread_entities").select("*").eq(
                    "user_id", user_id
                ).eq("entity_type", entity_type.value).gte(
                    "mentioned_at", cutoff
                ).order("mentioned_at", desc=True).limit(1).execute()
                
                if result.data:
                    row = result.data[0]
                    return Entity(
                        type=EntityType(row["entity_type"]),
                        value=row["entity_value"],
                        confidence=row["confidence"],
                        mentioned_at=datetime.fromisoformat(row["mentioned_at"])
                    )
            except Exception as e:
                logger.error("entity_resolve_failed", error=str(e))
        
        return None
    
    async def update_thread(
        self,
        thread_id: str,
        summary: str | None = None,
        pending_followup: str | None = None,
        new_entities: list[Entity] | None = None
    ):
        """Update a thread with new information."""
        if self._supabase:
            try:
                updates = {"last_message_at": datetime.now().isoformat()}
                if summary:
                    updates["summary"] = summary
                if pending_followup is not None:
                    updates["pending_followup"] = pending_followup
                
                await self._supabase.table("conversation_threads").update(
                    updates
                ).eq("id", thread_id).execute()
                
                # Add new entities
                if new_entities:
                    thread = self._thread_cache.get(thread_id)
                    user_id = thread.user_id if thread else None
                    
                    for entity in new_entities:
                        if user_id:
                            await self._supabase.table("thread_entities").insert({
                                "thread_id": thread_id,
                                "user_id": user_id,
                                "entity_type": entity.type.value,
                                "entity_value": entity.value,
                                "confidence": entity.confidence
                            }).execute()
                            
            except Exception as e:
                logger.error("thread_update_failed", error=str(e))
    
    # =========================================================================
    # L3: LONG-TERM PROFILE MEMORY
    # =========================================================================
    
    async def get_user_profile(self, user_id: str) -> dict:
        """Get user's long-term profile."""
        if user_id in self._profile_cache:
            return self._profile_cache[user_id]
        
        if self._supabase:
            try:
                result = await self._supabase.table("user_profiles").select("*").eq(
                    "user_id", user_id
                ).single().execute()
                
                if result.data:
                    self._profile_cache[user_id] = result.data
                    return result.data
            except Exception as e:
                logger.error("profile_fetch_failed", error=str(e))
        
        # Return default profile
        return {
            "preferred_language": "hinglish",
            "persona_mode": "girlfriend",
            "facts": {},
            "preferences": {}
        }
    
    async def save_memory_fact(
        self,
        user_id: str,
        fact: MemoryFact
    ):
        """Save a durable memory fact to the memories table."""
        if self._supabase:
            try:
                # Get current memories for user
                result = self._supabase.table("memories").select("facts,preferences").eq(
                    "user_id", user_id
                ).execute()
                
                if result.data:
                    current_facts = result.data[0].get("facts") or []
                    current_prefs = result.data[0].get("preferences") or {}
                    
                    # Create fact dict
                    fact_dict = {
                        "category": fact.category.value,
                        "key": fact.fact_key,
                        "value": fact.fact_value,
                        "confidence": fact.confidence,
                        "source": fact.source,
                    }
                    
                    # Check if fact already exists (update) or add new
                    updated = False
                    for i, f in enumerate(current_facts):
                        if f.get("key") == fact.fact_key and f.get("category") == fact.category.value:
                            current_facts[i] = fact_dict
                            updated = True
                            break
                    
                    if not updated:
                        current_facts.append(fact_dict)
                    
                    # Also update preferences if it's a preference
                    if fact.category.value == "preference":
                        current_prefs[fact.fact_key] = fact.fact_value
                    
                    # Update the memories table
                    self._supabase.table("memories").update({
                        "facts": current_facts,
                        "preferences": current_prefs,
                        "updated_at": "now()"
                    }).eq("user_id", user_id).execute()
                    
                    logger.info(
                        "memory_fact_saved",
                        category=fact.category.value,
                        key=fact.fact_key,
                        value=fact.fact_value
                    )
                else:
                    logger.warning("no_memory_record_for_user", user_id=user_id)
                    
            except Exception as e:
                logger.error("fact_save_failed", error=str(e))
    
    async def get_memory_facts(
        self,
        user_id: str,
        category: MemoryCategory | None = None,
        limit: int = 20
    ) -> list[MemoryFact]:
        """Get user's memory facts from memories table."""
        facts = []
        
        if self._supabase:
            try:
                result = self._supabase.table("memories").select("facts").eq(
                    "user_id", user_id
                ).execute()
                
                if result.data and result.data[0].get("facts"):
                    for fact_dict in result.data[0]["facts"][:limit]:
                        if category and fact_dict.get("category") != category.value:
                            continue
                        facts.append(MemoryFact(
                            category=MemoryCategory(fact_dict.get("category", "personal")),
                            fact_key=fact_dict.get("key", ""),
                            fact_value=fact_dict.get("value", ""),
                            confidence=fact_dict.get("confidence", 0.8),
                            source=fact_dict.get("source", "conversation"),
                        ))
            except Exception as e:
                logger.error("facts_fetch_failed", error=str(e))
        
        return facts
    
    # =========================================================================
    # L4: SEMANTIC RECALL (EMBEDDINGS)
    # =========================================================================
    
    async def create_embedding(self, text: str) -> list[float] | None:
        """Create embedding for text using OpenAI."""
        if not self._openai:
            return None
        
        try:
            response = await self._openai.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error("embedding_create_failed", error=str(e))
            return None
    
    async def store_embedding(
        self,
        user_id: str,
        source_type: str,
        content_text: str,
        content_summary: str | None = None,
        source_id: str | None = None
    ):
        """Store an embedding for semantic recall."""
        embedding = await self.create_embedding(content_text)
        if not embedding:
            return
        
        if self._supabase:
            try:
                await self._supabase.table("memory_embeddings").insert({
                    "user_id": user_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "content_text": content_text,
                    "content_summary": content_summary,
                    "embedding": embedding
                }).execute()
            except Exception as e:
                logger.error("embedding_store_failed", error=str(e))
    
    async def semantic_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        threshold: float = 0.7
    ) -> list[dict]:
        """Search memories by semantic similarity."""
        embedding = await self.create_embedding(query)
        if not embedding:
            return []
        
        if self._supabase:
            try:
                # Use pgvector similarity search
                result = await self._supabase.rpc(
                    "find_similar_memories",
                    {
                        "p_user_id": user_id,
                        "p_embedding": embedding,
                        "p_limit": limit,
                        "p_threshold": threshold
                    }
                ).execute()
                
                return result.data or []
            except Exception as e:
                logger.error("semantic_search_failed", error=str(e))
        
        return []
    
    # =========================================================================
    # L5: ANTI-REPETITION MEMORY
    # =========================================================================
    
    def _hash_pattern(self, pattern: str) -> str:
        """Create hash for pattern comparison."""
        return hashlib.md5(pattern.lower().strip().encode()).hexdigest()[:16]
    
    async def check_pattern_recent(
        self,
        user_id: str,
        pattern_type: str,
        pattern: str,
        hours_back: int = 24
    ) -> bool:
        """Check if a pattern was recently used."""
        pattern_hash = self._hash_pattern(pattern)
        
        # Check Redis first (faster)
        if self._redis:
            try:
                key = f"antirep:{user_id}:{pattern_type}:{pattern_hash}"
                exists = await self._redis.exists(key)
                if exists:
                    return True
            except:
                pass
        
        # Check database
        if self._supabase:
            try:
                result = await self._supabase.rpc(
                    "is_pattern_recent",
                    {
                        "p_user_id": user_id,
                        "p_pattern_type": pattern_type,
                        "p_pattern_hash": pattern_hash,
                        "p_hours_back": hours_back
                    }
                ).execute()
                return result.data
            except:
                pass
        
        return False
    
    async def log_pattern_usage(
        self,
        user_id: str,
        pattern_type: str,
        pattern: str,
        session_id: str | None = None
    ):
        """Log that a pattern was used."""
        pattern_hash = self._hash_pattern(pattern)
        
        # Store in Redis with TTL
        if self._redis:
            try:
                key = f"antirep:{user_id}:{pattern_type}:{pattern_hash}"
                await self._redis.setex(key, self.session_ttl, "1")
            except:
                pass
        
        # Also store in database for longer-term tracking
        if self._supabase:
            try:
                await self._supabase.table("anti_repetition_log").insert({
                    "user_id": user_id,
                    "session_id": session_id,
                    "pattern_type": pattern_type,
                    "pattern_value": pattern,
                    "pattern_hash": pattern_hash
                }).execute()
            except:
                pass
    
    async def get_fresh_opener(
        self,
        user_id: str,
        session_id: str,
        emotion: str,
        available_openers: list[str]
    ) -> str:
        """Get an opener that hasn't been used recently."""
        state = await self.get_session_state(user_id, session_id)
        
        for opener in available_openers:
            if not state.is_opener_recent(opener):
                is_db_recent = await self.check_pattern_recent(
                    user_id, "opener", opener, hours_back=48
                )
                if not is_db_recent:
                    # Log usage and return
                    state.add_opener(opener)
                    await self.save_session_state(state)
                    await self.log_pattern_usage(user_id, "opener", opener, session_id)
                    return opener
        
        # If all are recent, return the first one anyway
        return available_openers[0] if available_openers else ""
    
    # =========================================================================
    # L6: SUMMARIES AND EVENTS
    # =========================================================================
    
    async def create_session_summary(
        self,
        user_id: str,
        session_id: str,
        summary_text: str,
        key_topics: list[str],
        key_entities: list[dict]
    ):
        """Create a summary for a session."""
        if self._supabase:
            try:
                # Create embedding for semantic search
                embedding = await self.create_embedding(summary_text)
                
                await self._supabase.table("memory_summaries").insert({
                    "user_id": user_id,
                    "summary_type": "session",
                    "session_id": session_id,
                    "summary_text": summary_text,
                    "key_topics": key_topics,
                    "key_entities": key_entities,
                    "embedding": embedding
                }).execute()
                
                logger.info("session_summary_created", session_id=session_id)
            except Exception as e:
                logger.error("summary_create_failed", error=str(e))
    
    async def save_important_event(
        self,
        user_id: str,
        event_type: str,
        title: str,
        description: str | None = None,
        event_date: datetime | None = None,
        is_recurring: bool = False
    ):
        """Save an important event."""
        if self._supabase:
            try:
                await self._supabase.table("important_events").insert({
                    "user_id": user_id,
                    "event_type": event_type,
                    "event_title": title,
                    "event_description": description,
                    "event_date": event_date.date().isoformat() if event_date else None,
                    "is_recurring": is_recurring
                }).execute()
                
                logger.info("event_saved", event_type=event_type, title=title)
            except Exception as e:
                logger.error("event_save_failed", error=str(e))
    
    async def get_upcoming_events(
        self,
        user_id: str,
        days_ahead: int = 7
    ) -> list[dict]:
        """Get upcoming events for reminder."""
        events = []
        
        if self._supabase:
            try:
                cutoff = (datetime.now() + timedelta(days=days_ahead)).date().isoformat()
                result = await self._supabase.table("important_events").select("*").eq(
                    "user_id", user_id
                ).lte("event_date", cutoff).execute()
                
                events = result.data or []
            except Exception as e:
                logger.error("events_fetch_failed", error=str(e))
        
        return events
    
    # =========================================================================
    # COMPREHENSIVE MEMORY RETRIEVAL
    # =========================================================================
    
    async def retrieve_context_for_response(
        self,
        user_id: str,
        session_id: str,
        current_message: str,
        detected_emotion: str | None = None,
        detected_entities: list[Entity] | None = None
    ) -> dict:
        """
        Retrieve all relevant context for generating a response.
        
        Follows the retrieval order:
        1. Current turn buffer (L0)
        2. Short-term session state (L1)
        3. Active thread memory (L2)
        4. Recent entity memory
        5. Long-term profile (L3)
        6. Semantic recall (L4)
        7. Anti-repetition data (L5)
        """
        context = {
            "turn_buffer": None,
            "session_state": None,
            "active_threads": [],
            "resolved_entities": {},
            "user_profile": {},
            "relevant_facts": [],
            "semantic_matches": [],
            "recent_patterns": {},
            "upcoming_events": []
        }
        
        # L0: Turn buffer
        context["turn_buffer"] = self.get_turn_buffer(session_id)
        
        # L1: Session state
        session_state = await self.get_session_state(user_id, session_id)
        context["session_state"] = session_state
        
        # L2: Active threads
        threads = await self.get_active_threads(user_id)
        context["active_threads"] = threads
        
        # Resolve any entity references
        if detected_entities:
            for entity in detected_entities:
                context["resolved_entities"][entity.type.value] = entity
        
        # L3: User profile
        context["user_profile"] = await self.get_user_profile(user_id)
        
        # L3: Relevant facts
        context["relevant_facts"] = await self.get_memory_facts(user_id, limit=10)
        
        # L4: Semantic recall (if message seems to reference past)
        reference_words = ["वो", "उस", "वाली", "वाला", "that", "the one", "remember"]
        if any(word in current_message.lower() for word in reference_words):
            context["semantic_matches"] = await self.semantic_search(
                user_id, current_message, limit=3
            )
        
        # L5: Anti-repetition data
        context["recent_patterns"] = {
            "openers": session_state.recent_openers[-5:],
            "topics": session_state.recent_topics[-5:],
            "patterns": session_state.recent_patterns[-5:]
        }
        
        # L6: Upcoming events
        context["upcoming_events"] = await self.get_upcoming_events(user_id, days_ahead=3)
        
        return context
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _session_state_to_dict(self, state: SessionState) -> dict:
        """Convert SessionState to dict for storage."""
        return {
            "user_id": state.user_id,
            "session_id": state.session_id,
            "recent_messages": state.recent_messages,
            "active_topic": state.active_topic,
            "current_emotional_state": state.current_emotional_state,
            "pending_followup": state.pending_followup,
            "active_entities": {
                k: self._entity_to_dict(v) for k, v in state.active_entities.items()
            },
            "active_thread_ids": state.active_thread_ids,
            "recent_openers": state.recent_openers,
            "recent_patterns": state.recent_patterns,
            "recent_topics": state.recent_topics,
            "created_at": state.created_at.isoformat(),
            "last_activity_at": state.last_activity_at.isoformat()
        }
    
    def _dict_to_session_state(self, data: dict) -> SessionState:
        """Convert dict to SessionState."""
        state = SessionState(
            user_id=data["user_id"],
            session_id=data["session_id"]
        )
        state.recent_messages = data.get("recent_messages", [])
        state.active_topic = data.get("active_topic")
        state.current_emotional_state = data.get("current_emotional_state", "neutral")
        state.pending_followup = data.get("pending_followup")
        state.active_entities = {
            k: self._dict_to_entity(v) for k, v in data.get("active_entities", {}).items()
        }
        state.active_thread_ids = data.get("active_thread_ids", [])
        state.recent_openers = data.get("recent_openers", [])
        state.recent_patterns = data.get("recent_patterns", [])
        state.recent_topics = data.get("recent_topics", [])
        return state
    
    def _entity_to_dict(self, entity: Entity) -> dict:
        """Convert Entity to dict."""
        return {
            "type": entity.type.value,
            "value": entity.value,
            "confidence": entity.confidence,
            "metadata": entity.metadata,
            "mentioned_at": entity.mentioned_at.isoformat()
        }
    
    def _dict_to_entity(self, data: dict) -> Entity:
        """Convert dict to Entity."""
        return Entity(
            type=EntityType(data["type"]),
            value=data["value"],
            confidence=data.get("confidence", 0.8),
            metadata=data.get("metadata", {}),
            mentioned_at=datetime.fromisoformat(data["mentioned_at"]) if data.get("mentioned_at") else datetime.now()
        )
    
    def _dict_to_thread(self, data: dict) -> ConversationThread:
        """Convert dict to ConversationThread."""
        return ConversationThread(
            id=data["id"],
            user_id=data["user_id"],
            thread_type=ThreadType(data["thread_type"]),
            title=data["title"],
            status=data.get("status", "active"),
            summary=data.get("summary", ""),
            entities=[self._dict_to_entity(e) for e in data.get("entities", [])],
            pending_followup=data.get("pending_followup"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(),
            last_message_at=datetime.fromisoformat(data["last_message_at"]) if data.get("last_message_at") else datetime.now()
        )
