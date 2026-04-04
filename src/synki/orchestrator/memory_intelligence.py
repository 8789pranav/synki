"""
Memory Intelligence System

Smart memory extraction and classification using LLM.
Extracts meaningful facts from conversation and classifies their importance.

This module:
1. Tracks conversation history per session
2. Uses LLM to extract memories from user messages
3. Classifies memories by type and importance
4. Provides context management for conversations
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MemoryType(str, Enum):
    """Types of memories that can be extracted"""
    PREFERENCE = "preference"      # "I like pizza", "I hate mornings"
    PERSONAL = "personal"          # Name, age, location, job
    RELATIONSHIP = "relationship"  # Family, friends, relationships
    HEALTH = "health"              # Health conditions, fitness
    INTEREST = "interest"          # Hobbies, interests
    ROUTINE = "routine"            # Daily habits, schedules
    EMOTIONAL = "emotional"        # Emotional states, feelings
    EVENT = "event"                # Life events, milestones
    GOAL = "goal"                  # Goals, aspirations
    OTHER = "other"


class ImportanceLevel(str, Enum):
    """Importance levels for memories"""
    CRITICAL = "critical"  # Must remember (name, significant other, etc.)
    HIGH = "high"          # Important (job, location, close family)
    MEDIUM = "medium"      # Useful (preferences, hobbies)
    LOW = "low"            # Nice to know (minor details)
    SKIP = "skip"          # Not worth storing


@dataclass
class ExtractedMemory:
    """A memory extracted from conversation"""
    key: str                    # Short identifier
    value: str                  # The actual fact/memory
    memory_type: MemoryType
    importance: ImportanceLevel
    confidence: float = 0.8     # How confident we are (0-1)
    source_text: str = ""       # Original text it came from
    extracted_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.memory_type.value,
            "importance": self.importance.value,
            "confidence": self.confidence,
            "source": self.source_text,
            "extracted_at": self.extracted_at.isoformat(),
        }


class MemoryIntelligence:
    """
    Smart memory extraction using LLM.
    
    Tracks conversation history and extracts meaningful facts.
    """
    
    EXTRACTION_PROMPT = """You are a memory extraction system for a voice companion app.

Analyze this message from the user and extract any personal facts worth remembering.

EXTRACT:
- Personal details (name, age, job, location)
- Preferences (likes, dislikes, favorites)
- Relationships (family, friends, significant other)
- Health/fitness info
- Daily routines and habits
- Life events and milestones
- Goals and aspirations
- Emotional states (if significant)

DO NOT EXTRACT:
- Casual greetings ("hi", "hello")
- Generic chat ("how are you")
- Temporary states ("I'm eating lunch")
- Things already known (don't repeat)

IMPORTANT RULES:
- Use STANDARDIZED keys: favorite_food (not favorite_dish, favorite_cuisine for the same thing)
- Use favorite_movie, favorite_song, favorite_actor, favorite_color, etc.
- ONE fact per concept - don't create multiple entries for the same information
- If user says "I like pizza" - use key "favorite_food", value "pizza"
- If user says "my favorite movie is X" - use key "favorite_movie", value "X"

STANDARDIZED KEYS TO USE:
- name, age, birthday, location, job, company
- favorite_food, favorite_movie, favorite_song, favorite_color, favorite_actor
- hobby, interest, pet, relationship_status
- family_member (with value like "brother: Rahul")
- health_condition, allergy, fitness_goal

Respond in JSON format:
{{
    "memories": [
        {{
            "key": "standardized_key",
            "value": "the fact to remember",
            "type": "preference|personal|relationship|health|interest|routine|emotional|event|goal|other",
            "importance": "critical|high|medium|low|skip",
            "confidence": 0.8
        }}
    ]
}}

If nothing worth extracting, respond: {{"memories": []}}

ALREADY KNOWN FACTS (don't repeat these):
{known_facts}

USER MESSAGE:
{user_text}

RECENT CONVERSATION:
{conversation_history}"""

    def __init__(
        self,
        llm_client: Any = None,
        max_history: int = 10,
    ):
        """
        Initialize memory intelligence.
        
        Args:
            llm_client: OpenAI client for extraction
            max_history: Max messages to keep in history per session
        """
        self._llm = llm_client
        self._max_history = max_history
        self._session_history: dict[str, list[dict]] = {}
        
    def add_to_history(self, session_id: str, role: str, text: str):
        """Add a message to session history"""
        if session_id not in self._session_history:
            self._session_history[session_id] = []
        
        self._session_history[session_id].append({
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })
        
        # Trim to max history
        if len(self._session_history[session_id]) > self._max_history:
            self._session_history[session_id] = \
                self._session_history[session_id][-self._max_history:]
    
    def get_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session"""
        return self._session_history.get(session_id, [])
    
    def clear_history(self, session_id: str):
        """Clear history for a session"""
        if session_id in self._session_history:
            del self._session_history[session_id]
    
    async def extract_and_classify(
        self,
        session_id: str,
        user_text: str,
        known_facts: list[dict] | None = None,
    ) -> list[ExtractedMemory]:
        """
        Extract memories from user message using LLM.
        
        Args:
            session_id: Current session ID
            user_text: User's message text
            known_facts: Already known facts (to avoid duplicates)
            
        Returns:
            List of extracted memories
        """
        if not self._llm:
            logger.debug("no_llm_client_for_extraction")
            return []
        
        # Skip very short messages
        if len(user_text.strip()) < 5:
            return []
        
        # Add to history
        self.add_to_history(session_id, "user", user_text)
        
        # Build context
        history = self.get_history(session_id)
        history_text = "\n".join(
            f"{msg['role']}: {msg['text']}" for msg in history[-5:]
        )
        
        known_facts_text = ""
        if known_facts:
            known_facts_text = "\n".join(
                f"- {f.get('key', 'unknown')}: {f.get('value', '')}"
                for f in known_facts[:20]
            )
        
        prompt = self.EXTRACTION_PROMPT.format(
            user_text=user_text,
            conversation_history=history_text or "(no recent history)",
            known_facts=known_facts_text or "(none)",
        )
        
        try:
            logger.info("="*60)
            logger.info("🧠 MEMORY EXTRACTION - LLM Call")
            logger.info(f"   User Text: {user_text[:100]}...")
            logger.info(f"   History Length: {len(history)} messages")
            logger.info(f"   Known Facts: {len(known_facts) if known_facts else 0}")
            
            # Call LLM for extraction
            logger.info("   📡 Calling OpenAI GPT-4o-mini...")
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract memories from conversation. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            logger.info(f"   ✅ LLM Response received:")
            logger.info(f"      Raw content: {content[:200]}..." if len(content) > 200 else f"      Raw content: {content}")
            
            data = json.loads(content)
            logger.info(f"   ✅ JSON parsed successfully")
            logger.info(f"      Memories found: {len(data.get('memories', []))}")
            
            memories = []
            seen_keys = set()  # Track keys to avoid duplicates
            
            # Key normalization map - merge similar keys
            KEY_ALIASES = {
                "favorite_dish": "favorite_food",
                "favorite_cuisine": "favorite_food", 
                "favorite_meal": "favorite_food",
                "fav_food": "favorite_food",
                "favourite_food": "favorite_food",
                "favorite_film": "favorite_movie",
                "fav_movie": "favorite_movie",
                "favourite_movie": "favorite_movie",
                "favorite_music": "favorite_song",
                "fav_song": "favorite_song",
                "favourite_song": "favorite_song",
                "user_name": "name",
                "full_name": "name",
                "first_name": "name",
                "workplace": "company",
                "employer": "company",
                "work": "job",
                "occupation": "job",
                "profession": "job",
                "city": "location",
                "hometown": "location",
                "place": "location",
            }
            
            for mem in data.get("memories", []):
                # Skip if importance is "skip" or low confidence
                if mem.get("importance") == "skip":
                    continue
                if mem.get("confidence", 0.8) < 0.5:
                    continue
                
                # Normalize the key
                raw_key = mem.get("key", "unknown").lower().replace(" ", "_")
                normalized_key = KEY_ALIASES.get(raw_key, raw_key)
                
                # Skip if we already have this key
                if normalized_key in seen_keys:
                    logger.info(f"   ⚠️ Skipping duplicate key: {raw_key} -> {normalized_key}")
                    continue
                
                seen_keys.add(normalized_key)
                
                try:
                    memory = ExtractedMemory(
                        key=normalized_key,
                        value=mem.get("value", ""),
                        memory_type=MemoryType(mem.get("type", "other")),
                        importance=ImportanceLevel(mem.get("importance", "medium")),
                        confidence=float(mem.get("confidence", 0.8)),
                        source_text=user_text,
                    )
                    memories.append(memory)
                except (ValueError, KeyError) as e:
                    logger.debug("invalid_memory_data", error=str(e))
                    continue
            
            if memories:
                logger.info(f"   📝 EXTRACTED MEMORIES:")
                for i, m in enumerate(memories):
                    logger.info(f"      [{i+1}] {m.key}: {m.value} (type={m.memory_type.value}, importance={m.importance.value})")
            else:
                logger.info("   ℹ️ No memories worth storing from this message")
            
            logger.info("="*60)
            return memories
            
        except json.JSONDecodeError as e:
            logger.error(f"   ❌ JSON PARSE ERROR: {str(e)}")
            logger.error(f"   Raw content was: {content[:500] if 'content' in dir() else 'N/A'}")
            logger.info("="*60)
            return []
        except Exception as e:
            logger.error(f"   ❌ MEMORY EXTRACTION ERROR: {str(e)}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            logger.info("="*60)
            return []


class ConversationMemoryManager:
    """
    Manages conversation memories with database persistence.
    
    Combines MemoryIntelligence extraction with database storage.
    """
    
    def __init__(
        self,
        memory_intelligence: MemoryIntelligence,
        supabase_client: Any = None,
    ):
        """
        Initialize memory manager.
        
        Args:
            memory_intelligence: The extraction engine
            supabase_client: Database client for persistence
        """
        self.memory_intelligence = memory_intelligence
        self._supabase = supabase_client
    
    async def process_user_message(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
    ) -> list[ExtractedMemory]:
        """
        Process a user message: extract and save memories.
        
        Args:
            user_id: User's ID
            session_id: Current session ID
            user_text: User's message
            
        Returns:
            List of newly extracted memories
        """
        # Get existing facts
        known_facts = await self.get_user_facts(user_id)
        
        # Extract new memories
        memories = await self.memory_intelligence.extract_and_classify(
            session_id, user_text, known_facts
        )
        
        # Save new memories
        if memories:
            await self.save_memories(user_id, memories)
        
        return memories
    
    async def get_user_facts(self, user_id: str) -> list[dict]:
        """Get all known facts for a user"""
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.table("memories").select("facts").eq(
                "user_id", user_id
            ).execute()
            
            if result.data:
                return result.data[0].get("facts", [])
            return []
        except Exception as e:
            logger.error("get_facts_failed", error=str(e))
            return []
    
    async def save_memories(
        self,
        user_id: str,
        memories: list[ExtractedMemory],
    ) -> bool:
        """Save extracted memories to database"""
        if not self._supabase or not memories:
            return False
        
        try:
            # Get current facts
            current_facts = await self.get_user_facts(user_id)
            
            # Add new memories
            for memory in memories:
                memory_dict = memory.to_dict()
                
                # Check for duplicates by key
                existing_keys = {f.get("key") for f in current_facts}
                if memory.key not in existing_keys:
                    current_facts.append(memory_dict)
                else:
                    # Update existing
                    for i, fact in enumerate(current_facts):
                        if fact.get("key") == memory.key:
                            current_facts[i] = memory_dict
                            break
            
            # Save back
            self._supabase.table("memories").upsert({
                "user_id": user_id,
                "facts": current_facts,
                "updated_at": datetime.now().isoformat(),
            }).execute()
            
            logger.info(
                "memories_saved",
                user_id=user_id,
                count=len(memories),
            )
            return True
            
        except Exception as e:
            logger.error("save_memories_failed", error=str(e))
            return False
    
    def get_relevant_context(
        self,
        user_facts: list[dict],
        keywords: list[str] | None = None,
        max_facts: int = 10,
    ) -> str:
        """
        Get relevant facts as context string for LLM.
        
        Args:
            user_facts: All user facts
            keywords: Keywords to filter by (optional)
            max_facts: Maximum facts to return
            
        Returns:
            Formatted context string
        """
        if not user_facts:
            return ""
        
        # Filter by importance first
        critical = [f for f in user_facts if f.get("importance") == "critical"]
        high = [f for f in user_facts if f.get("importance") == "high"]
        medium = [f for f in user_facts if f.get("importance") == "medium"]
        
        # Prioritize critical and high importance
        selected = critical + high
        
        # Add medium if we have room
        remaining = max_facts - len(selected)
        if remaining > 0:
            selected.extend(medium[:remaining])
        
        # If keywords provided, boost relevant facts
        if keywords:
            keyword_set = set(k.lower() for k in keywords)
            
            def is_relevant(fact: dict) -> bool:
                text = f"{fact.get('key', '')} {fact.get('value', '')}".lower()
                return any(k in text for k in keyword_set)
            
            relevant = [f for f in selected if is_relevant(f)]
            other = [f for f in selected if not is_relevant(f)]
            selected = relevant + other
        
        # Format as context string
        lines = []
        for fact in selected[:max_facts]:
            key = fact.get("key", "unknown")
            value = fact.get("value", "")
            lines.append(f"- {key}: {value}")
        
        return "\n".join(lines)
