"""
Realtime Context Manager

Optimized system for managing conversation context without blocking responses.

Key Features:
1. FAST PATH: Cached context for instant response (no LLM delay)
2. BACKGROUND: Memory extraction runs after response
3. SMART INJECTION: Only relevant context injected into prompts

Architecture:
- ContextCache: In-memory cache of user facts (refreshed periodically)
- ResponseHints: Fast hints for persona/emotion (no LLM needed)
- BackgroundProcessor: Async tasks for memory extraction
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


class ResponseStyle(str, Enum):
    """Response style based on emotion/intent"""
    SUPPORTIVE = "supportive"      # User is sad/stressed
    PLAYFUL = "playful"            # User is happy/casual
    CURIOUS = "curious"            # User shared something interesting
    EMPATHETIC = "empathetic"      # User is venting
    EXCITED = "excited"            # User shared good news
    CALM = "calm"                  # User is anxious
    NORMAL = "normal"              # Default


@dataclass
class ContextCache:
    """Cached context for a user - refreshed periodically"""
    user_id: str
    facts: list[dict] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    name: str = "जानू"
    last_emotion: str = "neutral"
    last_topics: list[str] = field(default_factory=list)
    cached_at: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 300  # 5 minute cache
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.cached_at).seconds > self.ttl_seconds
    
    def get_relevant_facts(self, keywords: list[str], max_facts: int = 5) -> list[dict]:
        """Get facts relevant to current conversation (fast, no LLM)"""
        if not keywords:
            # Return high-importance facts by default
            return [f for f in self.facts if f.get("importance") in ["critical", "high"]][:max_facts]
        
        relevant = []
        for fact in self.facts:
            key = fact.get("key", "").lower()
            value = str(fact.get("value", "")).lower()
            for kw in keywords:
                if kw.lower() in key or kw.lower() in value:
                    relevant.append(fact)
                    break
        
        return relevant[:max_facts]


@dataclass
class ResponseHints:
    """Fast hints for response generation (no LLM needed)"""
    style: ResponseStyle = ResponseStyle.NORMAL
    warmth: str = "medium"
    should_ask_question: bool = False
    opener_suggestion: str | None = None
    avoid_topics: list[str] = field(default_factory=list)
    context_injection: str = ""
    emotion: str = "neutral"
    intent: str = "casual_chat"


@dataclass 
class ChatTurn:
    """A single turn in conversation"""
    role: str  # "user" or "assistant"
    content: str
    emotion: str = "neutral"
    timestamp: datetime = field(default_factory=datetime.now)


class RealtimeContextManager:
    """
    Manages conversation context with optimized latency.
    
    Two modes:
    1. FAST PATH: Get cached context instantly for response
    2. BACKGROUND: Update cache and extract memories async
    """
    
    def __init__(
        self,
        supabase_client: Any | None = None,
        openai_client: Any | None = None,
        emotion_detector: Any | None = None,
        intent_detector: Any | None = None,
        persona_engine: Any | None = None,
        response_planner: Any | None = None,
    ):
        self._supabase = supabase_client
        self._openai = openai_client
        self._emotion_detector = emotion_detector
        self._intent_detector = intent_detector
        self._persona_engine = persona_engine
        self._response_planner = response_planner
        
        # Caches
        self._context_cache: dict[str, ContextCache] = {}
        self._chat_history: dict[str, list[ChatTurn]] = {}
        
        # Background task queue
        self._background_tasks: list[asyncio.Task] = []
        
        logger.info("realtime_context_manager_initialized")
    
    # =========================================================================
    # FAST PATH - No blocking, instant response
    # =========================================================================
    
    def get_response_hints(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
    ) -> ResponseHints:
        """
        Get response hints FAST (< 20ms).
        Uses pattern matching, no LLM calls.
        """
        logger.info("="*60)
        logger.info("🎯 GET_RESPONSE_HINTS - FAST PATH")
        logger.info(f"   User ID: {user_id}")
        logger.info(f"   Session: {session_id}")
        logger.info(f"   User Text: {user_text[:100]}..." if len(user_text) > 100 else f"   User Text: {user_text}")
        
        hints = ResponseHints()
        
        # Detect emotion (fast regex)
        if self._emotion_detector:
            emotion, confidence = self._emotion_detector.detect(user_text)
            hints.emotion = emotion.value
            
            # Map emotion to style
            style_map = {
                "sad": ResponseStyle.SUPPORTIVE,
                "stressed": ResponseStyle.SUPPORTIVE,
                "anxious": ResponseStyle.CALM,
                "angry": ResponseStyle.EMPATHETIC,
                "happy": ResponseStyle.PLAYFUL,
                "excited": ResponseStyle.EXCITED,
                "bored": ResponseStyle.CURIOUS,
            }
            hints.style = style_map.get(emotion.value, ResponseStyle.NORMAL)
        
        # Detect intent (fast regex)
        if self._intent_detector:
            intent, confidence = self._intent_detector.detect(user_text)
            hints.intent = intent.value
            
            # Adjust for intent
            if intent.value == "venting":
                hints.should_ask_question = False
                hints.warmth = "high"
            elif intent.value == "question":
                hints.should_ask_question = False  # Answer first
            elif intent.value == "greeting":
                hints.should_ask_question = True
                hints.warmth = "high"
        
        # Get cached context for injection
        cache = self._get_or_create_cache(user_id)
        hints.context_injection = self._build_context_injection(cache, user_text)
        
        logger.info("📊 HINTS GENERATED:")
        logger.info(f"   Style: {hints.style.value}")
        logger.info(f"   Emotion: {hints.emotion}")
        logger.info(f"   Intent: {hints.intent}")
        logger.info(f"   Warmth: {hints.warmth}")
        logger.info(f"   Ask Question: {hints.should_ask_question}")
        logger.info(f"   Context Injection Length: {len(hints.context_injection)} chars")
        if hints.context_injection:
            logger.info(f"📝 CONTEXT INJECTION:")
            for line in hints.context_injection.split('\n'):
                logger.info(f"   {line}")
        logger.info("="*60)
        
        return hints
    
    def _build_context_injection(self, cache: ContextCache, user_text: str) -> str:
        """Build context string to inject into prompt (fast)"""
        logger.info("🔧 BUILDING CONTEXT INJECTION")
        logger.info(f"   Cache User: {cache.user_id}")
        logger.info(f"   Cache Name: {cache.name}")
        logger.info(f"   Total Facts in Cache: {len(cache.facts)}")
        
        lines = []
        
        # Add user name
        if cache.name and cache.name != "जानू":
            lines.append(f"User का नाम: {cache.name}")
            logger.info(f"   ✓ Added name: {cache.name}")
        
        # Extract keywords from user text for relevance
        keywords = self._extract_keywords(user_text)
        logger.info(f"   Extracted Keywords: {keywords}")
        
        # Get relevant facts
        relevant_facts = cache.get_relevant_facts(keywords, max_facts=3)
        logger.info(f"   Relevant Facts Found: {len(relevant_facts)}")
        
        if relevant_facts:
            lines.append("याद रखो:")
            for fact in relevant_facts:
                key = fact.get("key", "").replace("_", " ")
                value = fact.get("value", "")
                importance = fact.get("importance", "unknown")
                lines.append(f"  - {key}: {value}")
                logger.info(f"   📌 Fact: {key} = {value} (importance: {importance})")
        else:
            logger.info("   ⚠️ No relevant facts found for injection")
        
        # Log all cached facts for debugging
        if cache.facts:
            logger.info(f"   📚 ALL CACHED FACTS ({len(cache.facts)} total):")
            for i, fact in enumerate(cache.facts[:10]):  # Show first 10
                logger.info(f"      [{i+1}] {fact.get('key', '?')}: {fact.get('value', '?')[:50]}")
            if len(cache.facts) > 10:
                logger.info(f"      ... and {len(cache.facts) - 10} more facts")
        
        return "\n".join(lines) if lines else ""
    
    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords for relevance matching (fast, no LLM)"""
        # Common topic words in Hindi/Hinglish
        keywords = []
        
        topic_patterns = {
            "movie": ["movie", "film", "picture", "देखी", "देखना", "शो"],
            "food": ["food", "खाना", "खाने", "recipe", "dish", "biryani", "pizza"],
            "work": ["work", "job", "काम", "office", "boss", "meeting"],
            "health": ["health", "medicine", "दवाई", "doctor", "tablet", "बीमार"],
            "family": ["family", "mom", "dad", "मम्मी", "पापा", "brother", "sister"],
            "music": ["music", "song", "गाना", "singer", "album"],
        }
        
        text_lower = text.lower()
        for topic, patterns in topic_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    keywords.append(topic)
                    break
        
        return keywords
    
    def add_turn(self, session_id: str, role: str, content: str, emotion: str = "neutral"):
        """Add a turn to chat history (fast)"""
        if session_id not in self._chat_history:
            self._chat_history[session_id] = []
        
        self._chat_history[session_id].append(ChatTurn(
            role=role,
            content=content,
            emotion=emotion,
        ))
        
        # Keep only last 10 turns
        if len(self._chat_history[session_id]) > 10:
            self._chat_history[session_id] = self._chat_history[session_id][-10:]
    
    def get_chat_history(self, session_id: str, max_turns: int = 5) -> list[dict]:
        """Get recent chat history for context"""
        history = self._chat_history.get(session_id, [])
        return [
            {"role": t.role, "content": t.content}
            for t in history[-max_turns:]
        ]
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def _get_or_create_cache(self, user_id: str) -> ContextCache:
        """Get cached context or create new"""
        if user_id in self._context_cache:
            cache = self._context_cache[user_id]
            if not cache.is_expired():
                return cache
        
        # Create empty cache (will be populated in background)
        cache = ContextCache(user_id=user_id)
        self._context_cache[user_id] = cache
        return cache
    
    async def refresh_cache(self, user_id: str) -> ContextCache:
        """Refresh cache from database (call in background)"""
        logger.info("="*60)
        logger.info("🔄 REFRESH_CACHE - Loading from Database")
        logger.info(f"   User ID: {user_id}")
        
        if not self._supabase:
            logger.warning("   ⚠️ No Supabase client - using empty cache")
            return self._get_or_create_cache(user_id)
        
        try:
            logger.info("   📡 Querying Supabase memories table...")
            result = self._supabase.table("memories").select(
                "name,facts,preferences"
            ).eq("user_id", user_id).execute()
            
            if result.data:
                data = result.data[0]
                cache = ContextCache(
                    user_id=user_id,
                    name=data.get("name", "जानू"),
                    facts=data.get("facts", []),
                    preferences=data.get("preferences", {}),
                    cached_at=datetime.now(),
                )
                self._context_cache[user_id] = cache
                
                logger.info("   ✅ CACHE LOADED FROM DATABASE:")
                logger.info(f"      Name: {cache.name}")
                logger.info(f"      Facts Count: {len(cache.facts)}")
                logger.info(f"      Preferences: {cache.preferences}")
                
                if cache.facts:
                    logger.info("   📚 FACTS FROM DATABASE:")
                    for i, fact in enumerate(cache.facts):
                        logger.info(f"      [{i+1}] {fact.get('key', '?')}: {fact.get('value', '?')[:80]}")
                else:
                    logger.info("   ⚠️ No facts in database for this user")
                
                logger.info("="*60)
                return cache
            else:
                logger.warning(f"   ⚠️ No data found for user {user_id}")
                
        except Exception as e:
            logger.error(f"   ❌ CACHE REFRESH FAILED: {str(e)}")
        
        logger.info("="*60)
        return self._get_or_create_cache(user_id)
    
    # =========================================================================
    # BACKGROUND PROCESSING - Runs after response sent
    # =========================================================================
    
    def schedule_background_task(self, coro):
        """Schedule a coroutine to run in background"""
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        
        # Cleanup completed tasks
        self._background_tasks = [t for t in self._background_tasks if not t.done()]
    
    async def process_turn_background(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        memory_intelligence: Any | None = None,
    ):
        """
        Background processing after response is sent.
        
        This handles:
        1. Memory extraction (LLM call)
        2. Cache refresh
        3. Thread tracking
        """
        try:
            logger.info("="*60)
            logger.info("🔮 BACKGROUND PROCESSING - Memory Extraction")
            logger.info(f"   User ID: {user_id}")
            logger.info(f"   Session: {session_id}")
            logger.info(f"   Text: {user_text[:100]}..." if len(user_text) > 100 else f"   Text: {user_text}")
            
            # Extract and save memories
            if memory_intelligence:
                # Get existing facts from cache to avoid duplicates
                cache = self._get_or_create_cache(user_id)
                known_facts = cache.facts if cache.facts else []
                logger.info(f"   📚 Known facts count: {len(known_facts)}")
                
                logger.info("   🧠 Calling LLM for memory extraction...")
                memories = await memory_intelligence.extract_and_classify(
                    session_id, user_text, known_facts=known_facts
                )
                
                if memories:
                    logger.info(f"   ✅ EXTRACTED {len(memories)} MEMORIES:")
                    for i, memory in enumerate(memories):
                        logger.info(f"      [{i+1}] Key: {memory.key}")
                        logger.info(f"          Value: {memory.value}")
                        logger.info(f"          Type: {memory.memory_type.value}")
                        logger.info(f"          Importance: {memory.importance.value}")
                        logger.info(f"          Confidence: {memory.confidence}")
                    
                    # Save to database
                    logger.info("   💾 Saving memories to database...")
                    for memory in memories:
                        await self._save_memory(user_id, memory)
                    
                    # Refresh cache with new data
                    logger.info("   🔄 Refreshing cache with new data...")
                    await self.refresh_cache(user_id)
                    
                    logger.info(f"   ✅ BACKGROUND COMPLETE - {len(memories)} memories saved")
                else:
                    logger.info("   ℹ️ No new memories extracted from this message")
            else:
                logger.warning("   ⚠️ No memory_intelligence provided - skipping extraction")
            
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"   ❌ BACKGROUND PROCESSING FAILED: {str(e)}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
    
    async def _save_memory(self, user_id: str, memory):
        """Save a memory to database"""
        logger.info(f"   💾 SAVING MEMORY: {memory.key}")
        
        if not self._supabase:
            logger.warning("      ⚠️ No Supabase client - cannot save")
            return
        
        try:
            # Get current facts
            logger.info(f"      📡 Fetching current facts for user...")
            result = self._supabase.table("memories").select("facts").eq(
                "user_id", user_id
            ).execute()
            
            if not result.data:
                logger.warning(f"      ⚠️ No memory record found for user {user_id}")
                return
            
            current_facts = result.data[0].get("facts", [])
            logger.info(f"      Current facts count: {len(current_facts)}")
            
            # Create new fact
            new_fact = {
                "category": memory.memory_type.value,
                "key": memory.key,
                "value": memory.value,
                "importance": memory.importance.value,
                "confidence": memory.confidence,
                "source": "conversation",
                "extracted_at": datetime.now().isoformat(),
            }
            
            # Update or add
            updated = False
            for i, f in enumerate(current_facts):
                if f.get("key") == memory.key:
                    current_facts[i] = new_fact
                    updated = True
                    break
            
            if not updated:
                current_facts.append(new_fact)
            
            # Save back
            logger.info(f"      📤 Saving updated facts (total: {len(current_facts)})...")
            self._supabase.table("memories").update({
                "facts": current_facts,
                "updated_at": "now()",
            }).eq("user_id", user_id).execute()
            logger.info(f"      ✅ Memory '{memory.key}' saved successfully!")
            
        except Exception as e:
            logger.error(f"      ❌ MEMORY SAVE FAILED: {str(e)}")
    
    # =========================================================================
    # INSTRUCTION BUILDING
    # =========================================================================
    
    def build_dynamic_instructions(
        self,
        base_instructions: str,
        hints: ResponseHints,
        chat_history: list[dict] | None = None,
    ) -> str:
        """
        Build dynamic instructions with context injection.
        
        This modifies the LLM prompt based on:
        - Detected emotion/intent
        - Cached user facts
        - Response style hints
        """
        logger.info("="*60)
        logger.info("📝 BUILD_DYNAMIC_INSTRUCTIONS")
        logger.info(f"   Base instructions length: {len(base_instructions)} chars")
        logger.info(f"   Style: {hints.style.value}")
        logger.info(f"   Emotion: {hints.emotion}")
        logger.info(f"   Chat history turns: {len(chat_history) if chat_history else 0}")
        
        parts = []
        
        # ADD CONTEXT/FACTS FIRST - so LLM sees user info immediately
        if hints.context_injection:
            parts.append(f"""⚠️ IMPORTANT - USER CONTEXT (इसे याद रखो और use करो):
{hints.context_injection}

तुम्हें user के बारे में ये facts पता हैं - इन्हें conversation में naturally use करो!""")
        
        # Then base instructions
        parts.append(base_instructions)
        
        # Add emotion-specific guidance
        if hints.style == ResponseStyle.SUPPORTIVE:
            parts.append("""
🔴 USER SEEMS SAD/STRESSED:
- Be extra gentle and supportive
- Use phrases like "मैं हूं ना", "सब ठीक होगा"
- Don't give advice unless asked
- Just listen and comfort""")
        
        elif hints.style == ResponseStyle.PLAYFUL:
            parts.append("""
🟢 USER IS HAPPY:
- Match their energy! Be playful
- Use teasing and humor
- Be enthusiastic and fun""")
        
        elif hints.style == ResponseStyle.EMPATHETIC:
            parts.append("""
🟠 USER IS VENTING:
- Just listen, don't lecture
- Validate their feelings
- Simple acknowledgments like "हां यार, समझ सकती हूं"
- NO advice unless they ask!""")
        
        elif hints.style == ResponseStyle.CALM:
            parts.append("""
🔵 USER SEEMS ANXIOUS:
- Be calm and reassuring
- Help them relax
- "Relax करो", "Deep breath लो"
- Be a calming presence""")
        
        # Add chat history summary
        if chat_history and len(chat_history) > 2:
            recent = chat_history[-3:]
            history_text = "\n".join([
                f"{'User' if m['role'] == 'user' else 'You'}: {m['content'][:50]}..."
                for m in recent
            ])
            parts.append(f"""
💬 RECENT CONVERSATION:
{history_text}""")
        
        # Response style hints
        parts.append(f"""
🎯 RESPONSE STYLE:
- Warmth level: {hints.warmth}
- Ask question: {"हां" if hints.should_ask_question else "नहीं"}
- Emotion detected: {hints.emotion}""")
        
        final_instructions = "\n\n".join(parts)
        logger.info(f"   📄 FINAL INSTRUCTIONS LENGTH: {len(final_instructions)} chars")
        logger.info("   📋 INSTRUCTIONS PREVIEW (first 500 chars):")
        for line in final_instructions[:500].split('\n'):
            logger.info(f"      {line}")
        if len(final_instructions) > 500:
            logger.info("      ... (truncated)")
        logger.info("="*60)
        
        return final_instructions


# Factory function
def create_realtime_context_manager(
    supabase_client: Any | None = None,
    openai_client: Any | None = None,
    orchestrator: Any | None = None,
) -> RealtimeContextManager:
    """Create a RealtimeContextManager with orchestrator components"""
    
    emotion_detector = None
    intent_detector = None
    persona_engine = None
    response_planner = None
    
    if orchestrator:
        emotion_detector = getattr(orchestrator, 'emotion_detector', None)
        intent_detector = getattr(orchestrator, 'intent_detector', None)
        persona_engine = getattr(orchestrator, 'persona_engine', None)
        response_planner = getattr(orchestrator, 'response_planner', None)
    
    return RealtimeContextManager(
        supabase_client=supabase_client,
        openai_client=openai_client,
        emotion_detector=emotion_detector,
        intent_detector=intent_detector,
        persona_engine=persona_engine,
        response_planner=response_planner,
    )
