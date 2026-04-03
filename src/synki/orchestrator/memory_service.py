"""
Memory Service

Handles long-term memory storage and retrieval for user personalization.
Uses Redis for persistence with configurable TTL.
"""

from datetime import datetime
from typing import Any

import structlog

from ..models import LanguageStyle, LongTermMemory

logger = structlog.get_logger(__name__)


class MemoryService:
    """Service for managing user long-term memory."""
    
    def __init__(self, redis_client: Any | None = None, memory_ttl: int = 86400 * 30):
        """
        Initialize memory service.
        
        Args:
            redis_client: Optional Redis client
            memory_ttl: Memory TTL in seconds (default: 30 days)
        """
        self._redis = redis_client
        self._memory_ttl = memory_ttl
        self._cache: dict[str, LongTermMemory] = {}
    
    async def get_memory(self, user_id: str) -> LongTermMemory:
        """
        Get user's long-term memory.
        
        Args:
            user_id: User identifier
            
        Returns:
            LongTermMemory instance
        """
        # Check cache first
        if user_id in self._cache:
            return self._cache[user_id]
        
        # Try Redis
        if self._redis:
            try:
                key = f"memory:{user_id}"
                data = await self._redis.get(key)
                if data:
                    memory = LongTermMemory.model_validate_json(data)
                    self._cache[user_id] = memory
                    return memory
            except Exception as e:
                logger.error("memory_load_failed", user_id=user_id, error=str(e))
        
        # Return new memory
        memory = LongTermMemory(user_id=user_id)
        self._cache[user_id] = memory
        return memory
    
    async def save_memory(self, memory: LongTermMemory) -> bool:
        """
        Save user's long-term memory.
        
        Args:
            memory: LongTermMemory to save
            
        Returns:
            True if saved successfully
        """
        memory.last_updated = datetime.now()
        self._cache[memory.user_id] = memory
        
        if self._redis:
            try:
                key = f"memory:{memory.user_id}"
                data = memory.model_dump_json()
                await self._redis.setex(key, self._memory_ttl, data)
                logger.info("memory_saved", user_id=memory.user_id)
                return True
            except Exception as e:
                logger.error("memory_save_failed", user_id=memory.user_id, error=str(e))
                return False
        
        return True
    
    async def update_memory(
        self,
        user_id: str,
        **updates: Any,
    ) -> LongTermMemory:
        """
        Update specific memory fields.
        
        Args:
            user_id: User identifier
            **updates: Fields to update
            
        Returns:
            Updated LongTermMemory
        """
        memory = await self.get_memory(user_id)
        
        for key, value in updates.items():
            if hasattr(memory, key):
                # Handle list fields specially - append instead of replace
                current = getattr(memory, key)
                if isinstance(current, list) and not isinstance(value, list):
                    if value not in current:
                        current.append(value)
                else:
                    setattr(memory, key, value)
        
        await self.save_memory(memory)
        return memory
    
    async def learn_from_conversation(
        self,
        user_id: str,
        user_text: str,
        topic: str,
    ) -> None:
        """
        Extract and store learnings from conversation.
        
        Args:
            user_id: User identifier
            user_text: User's message
            topic: Current topic
        """
        memory = await self.get_memory(user_id)
        text_lower = user_text.lower()
        
        # Learn sleep patterns
        if "late" in text_lower and ("sleep" in text_lower or "sone" in text_lower):
            memory.sleep_pattern = "late sleeper"
        elif "early" in text_lower and ("sleep" in text_lower or "sone" in text_lower):
            memory.sleep_pattern = "early sleeper"
        
        # Learn common states
        if topic == "work_stress" and "work_stress" not in memory.common_states:
            memory.common_states.append("work_stress")
        
        # Learn interests from topics
        interest_topics = ["entertainment", "food", "relationships"]
        if topic in interest_topics and topic not in memory.interests:
            memory.interests.append(topic)
        
        # Extract name if mentioned
        name_patterns = ["mera naam", "my name is", "i am", "main hoon"]
        for pattern in name_patterns:
            if pattern in text_lower:
                # Simple extraction - get word after pattern
                idx = text_lower.find(pattern)
                words_after = user_text[idx + len(pattern):].strip().split()
                if words_after:
                    potential_name = words_after[0].strip(".,!?")
                    if len(potential_name) > 1 and potential_name.isalpha():
                        memory.name = potential_name.capitalize()
        
        await self.save_memory(memory)
    
    def get_memory_facts(self, memory: LongTermMemory) -> list[str]:
        """
        Get relevant memory facts for LLM context.
        
        Args:
            memory: User's long-term memory
            
        Returns:
            List of memory fact strings
        """
        facts = []
        
        if memory.name:
            facts.append(f"User's name is {memory.name}")
        
        if memory.nickname:
            facts.append(f"User likes to be called {memory.nickname}")
        
        if memory.sleep_pattern:
            facts.append(f"User is a {memory.sleep_pattern}")
        
        if memory.common_states:
            states = ", ".join(memory.common_states[:3])
            facts.append(f"User often experiences: {states}")
        
        if memory.interests:
            interests = ", ".join(memory.interests[:3])
            facts.append(f"User is interested in: {interests}")
        
        if memory.preferred_language != LanguageStyle.HINGLISH:
            facts.append(f"User prefers {memory.preferred_language.value} style")
        
        return facts
    
    async def clear_memory(self, user_id: str) -> bool:
        """
        Clear user's long-term memory.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if cleared successfully
        """
        if user_id in self._cache:
            del self._cache[user_id]
        
        if self._redis:
            try:
                await self._redis.delete(f"memory:{user_id}")
            except Exception as e:
                logger.error("memory_clear_failed", user_id=user_id, error=str(e))
                return False
        
        return True
