"""
Anti-Repetition Checker

Prevents repetitive responses, openers, phrases, and patterns
to keep conversations fresh and natural.
"""

import hashlib
import random
from datetime import datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AntiRepetitionChecker:
    """
    Prevents repetitive responses and patterns in conversation.
    
    Tracks:
    - Greeting openers ("Haan baby", "Hiii", etc.)
    - Common phrases and expressions
    - Topic-specific responses
    - Question patterns
    """
    
    # Variety pools for different situations
    GREETING_OPENERS = [
        "Hiii baby!",
        "Haan batao",
        "Arre haan?",
        "Hmm? Bol na",
        "Hey! Kya hai?",
        "Arre kya hua?",
        "Haan jaan",
        "Batao batao",
        "Hmm? Sunao",
        "Bol baby bol",
        "Heyy",
        "Arre haan batao",
        "Kya baat hai?",
        "Hmm jaan?",
        "Arre tell me",
    ]
    
    AFFIRMATIVE_RESPONSES = [
        "Haan bilkul!",
        "Arre haan!",
        "Of course baby",
        "Haan na",
        "Definitely!",
        "Haan zaroor",
        "100%!",
        "Arre obviously",
        "Haan yaar",
        "Pakka!",
    ]
    
    SYMPATHY_OPENERS = [
        "Aww baby",
        "Arre no no",
        "Oh no",
        "Kya hua?",
        "Arre sad mat ho",
        "Hey hey it's okay",
        "Baby don't worry",
        "Suno na",
        "Koi baat nahi",
        "Main hoon na",
    ]
    
    EXCITED_RESPONSES = [
        "Omg yay!",
        "Arre waah!",
        "That's amazing!",
        "Sahi hai!",
        "Wow wow!",
        "Bahut achha!",
        "Kitna cute!",
        "Mast!",
        "Love it!",
        "So cool!",
    ]
    
    THINKING_FILLERS = [
        "Hmm let me think...",
        "Arre wait...",
        "Sochne do...",
        "Matlab...",
        "Basically...",
        "So like...",
        "Aise hai ki...",
        "Dekho...",
    ]
    
    QUESTION_STARTERS = [
        "Acha aur",
        "Btw",
        "Waise",
        "Aur batao",
        "Ek baat batao",
        "Tell me na",
        "By the way",
        "Oh and",
        "Acha ye batao",
        "One more thing",
    ]
    
    def __init__(
        self,
        redis_client: Any | None = None,
        supabase_client: Any | None = None
    ):
        """Initialize anti-repetition checker."""
        self._redis = redis_client
        self._supabase = supabase_client
        
        # In-memory recent tracking per session
        self._session_openers: dict[str, list[str]] = {}
        self._session_phrases: dict[str, list[str]] = {}
        self._session_topics: dict[str, list[str]] = {}
        
        logger.info("anti_repetition_checker_initialized")
    
    def _get_hash(self, text: str) -> str:
        """Get hash of normalized text."""
        normalized = text.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _normalize_phrase(self, phrase: str) -> str:
        """Normalize phrase for comparison."""
        # Remove extra whitespace
        normalized = " ".join(phrase.lower().split())
        
        # Remove common particles that don't affect meaning
        particles = ["na", "yaar", "baby", "jaan", "like", "you know"]
        words = normalized.split()
        words = [w for w in words if w not in particles]
        
        return " ".join(words)
    
    def get_fresh_opener(
        self,
        session_id: str,
        emotion: str | None = None,
        context: str | None = None
    ) -> str:
        """
        Get a greeting opener that hasn't been used recently.
        
        Args:
            session_id: Current session ID
            emotion: Current emotional context (sad, happy, neutral)
            context: Additional context about situation
            
        Returns:
            Fresh opener string
        """
        # Select pool based on emotion
        if emotion == "sad":
            pool = self.SYMPATHY_OPENERS.copy()
        elif emotion == "happy":
            pool = self.EXCITED_RESPONSES.copy()
        else:
            pool = self.GREETING_OPENERS.copy()
        
        # Get recently used openers
        recent = self._session_openers.get(session_id, [])
        recent_normalized = [self._normalize_phrase(o) for o in recent[-5:]]
        
        # Filter out recent ones
        available = [
            o for o in pool
            if self._normalize_phrase(o) not in recent_normalized
        ]
        
        # If all used, reset and pick random
        if not available:
            available = pool
        
        chosen = random.choice(available)
        
        # Track usage
        if session_id not in self._session_openers:
            self._session_openers[session_id] = []
        self._session_openers[session_id].append(chosen)
        
        # Keep only last 20
        if len(self._session_openers[session_id]) > 20:
            self._session_openers[session_id] = self._session_openers[session_id][-20:]
        
        return chosen
    
    def get_fresh_question_starter(self, session_id: str) -> str:
        """Get a fresh way to start a follow-up question."""
        recent = self._session_phrases.get(session_id, [])
        recent_normalized = [self._normalize_phrase(p) for p in recent[-5:]]
        
        available = [
            q for q in self.QUESTION_STARTERS
            if self._normalize_phrase(q) not in recent_normalized
        ]
        
        if not available:
            available = self.QUESTION_STARTERS
        
        chosen = random.choice(available)
        
        if session_id not in self._session_phrases:
            self._session_phrases[session_id] = []
        self._session_phrases[session_id].append(chosen)
        
        return chosen
    
    def is_phrase_repetitive(
        self,
        session_id: str,
        phrase: str,
        threshold: int = 2
    ) -> bool:
        """
        Check if a phrase has been used too recently.
        
        Args:
            session_id: Current session
            phrase: Phrase to check
            threshold: How many times is too many in recent history
            
        Returns:
            True if phrase is repetitive
        """
        recent = self._session_phrases.get(session_id, [])
        normalized = self._normalize_phrase(phrase)
        
        count = sum(
            1 for p in recent[-15:]
            if self._normalize_phrase(p) == normalized
        )
        
        return count >= threshold
    
    def track_phrase_usage(self, session_id: str, phrase: str):
        """Track that a phrase was used."""
        if session_id not in self._session_phrases:
            self._session_phrases[session_id] = []
        self._session_phrases[session_id].append(phrase)
        
        # Keep only last 30
        if len(self._session_phrases[session_id]) > 30:
            self._session_phrases[session_id] = self._session_phrases[session_id][-30:]
    
    def track_topic_usage(self, session_id: str, topic: str):
        """Track that a topic was discussed."""
        if session_id not in self._session_topics:
            self._session_topics[session_id] = []
        self._session_topics[session_id].append(topic)
        
        if len(self._session_topics[session_id]) > 20:
            self._session_topics[session_id] = self._session_topics[session_id][-20:]
    
    def is_topic_recent(self, session_id: str, topic: str) -> bool:
        """Check if topic was recently discussed."""
        recent = self._session_topics.get(session_id, [])
        normalized = topic.lower().strip()
        
        return any(
            normalized in t.lower() or t.lower() in normalized
            for t in recent[-5:]
        )
    
    async def check_pattern_in_db(
        self,
        user_id: str,
        pattern_type: str,
        pattern: str,
        hours_back: int = 24
    ) -> bool:
        """Check if pattern was recently used (database)."""
        if not self._supabase:
            return False
        
        try:
            pattern_hash = self._get_hash(pattern)
            cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
            
            result = await self._supabase.table("anti_repetition_log").select("id").eq(
                "user_id", user_id
            ).eq("pattern_type", pattern_type).eq(
                "pattern_hash", pattern_hash
            ).gte("used_at", cutoff).limit(1).execute()
            
            return len(result.data) > 0
        except Exception as e:
            logger.error("pattern_check_failed", error=str(e))
            return False
    
    async def log_pattern_to_db(
        self,
        user_id: str,
        session_id: str,
        pattern_type: str,
        pattern: str
    ):
        """Log pattern usage to database for longer-term tracking."""
        if not self._supabase:
            return
        
        try:
            await self._supabase.table("anti_repetition_log").insert({
                "user_id": user_id,
                "session_id": session_id,
                "pattern_type": pattern_type,
                "pattern_value": pattern,
                "pattern_hash": self._get_hash(pattern)
            }).execute()
        except Exception as e:
            logger.error("pattern_log_failed", error=str(e))
    
    def vary_response(self, response: str, session_id: str) -> str:
        """
        Add subtle variation to a response to make it less repetitive.
        
        Replaces common phrases with alternatives.
        """
        # Phrase variations
        variations = {
            "achha": ["acha", "ohh", "hmm okay", "I see"],
            "haan": ["ha", "yeah", "yes", "hmm"],
            "nahi": ["no", "nah", "nope", "nhi"],
            "kya": ["what", "क्या", "matlab"],
            "okay": ["ok", "acha okay", "theek hai", "fine"],
            "main bhi": ["me too", "same here", "mujhe bhi"],
        }
        
        result = response
        for original, alternatives in variations.items():
            if original in response.lower():
                # 30% chance to vary
                if random.random() < 0.3:
                    replacement = random.choice(alternatives)
                    import re
                    result = re.sub(
                        rf"\b{original}\b",
                        replacement,
                        result,
                        count=1,
                        flags=re.IGNORECASE
                    )
        
        # Add variation particle sometimes
        particles = ["na", "yaar", "like", "basically"]
        if random.random() < 0.2 and len(result) < 100:
            particle = random.choice(particles)
            # Add after first sentence
            if "." in result or "!" in result or "?" in result:
                for punct in [".", "!", "?"]:
                    if punct in result:
                        idx = result.index(punct) + 1
                        if idx < len(result):
                            result = result[:idx] + f" {particle.capitalize()}, " + result[idx:].lstrip()
                            break
        
        return result
    
    def clear_session(self, session_id: str):
        """Clear tracking for a session."""
        self._session_openers.pop(session_id, None)
        self._session_phrases.pop(session_id, None)
        self._session_topics.pop(session_id, None)
        logger.info("session_tracking_cleared", session_id=session_id)
