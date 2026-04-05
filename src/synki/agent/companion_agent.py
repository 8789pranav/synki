"""
Synki Companion Agent

Main LiveKit agent implementation that orchestrates the entire voice pipeline:
User Audio → Deepgram STT → Orchestrator → OpenAI LLM → Cartesia TTS → User Audio

OPTIMIZED ARCHITECTURE:
- FAST PATH: Instant response with cached context (no LLM delay)
- BACKGROUND: Memory extraction runs after response sent
- PROFILE SYSTEM: Short-term (rolling 6 days) + Long-term (permanent) profiles
- FULL INTEGRATION: Uses all orchestrator components

Components:
- RealtimeContextManager: Fast context injection (< 20ms)
- MemoryIntelligence: Background memory extraction
- UserProfileService: Short-term + Long-term psychological profiles
- EmotionDetector: Pattern-based emotion detection
- IntentDetector: Pattern-based intent detection
- PersonaEngine: Dynamic persona adjustment
- All components work together for personalized responses

Updated for LiveKit Agents SDK v1.5+
"""

import asyncio
import structlog
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io, TurnHandlingOptions, inference
from livekit.plugins import silero, cartesia, openai, deepgram

# Try to import turn detector, fall back gracefully
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel
    HAS_MULTILINGUAL = True
except ImportError:
    HAS_MULTILINGUAL = False

# Try to import noise cancellation, fall back gracefully
try:
    from livekit.plugins import noise_cancellation
    HAS_NOISE_CANCELLATION = True
except ImportError:
    HAS_NOISE_CANCELLATION = False

from ..config import settings
from ..models import PersonaProfile, EmotionState, IntentType
from ..orchestrator import EnhancedOrchestrator
from ..orchestrator.memory_intelligence import (
    MemoryIntelligence,
    ConversationMemoryManager,
    ImportanceLevel,
)
from ..orchestrator.realtime_context import (
    RealtimeContextManager,
    create_realtime_context_manager,
    ResponseHints,
    ResponseStyle,
)
from ..orchestrator.user_profile import (
    UserProfileService,
    ShortTermProfile,
    LongTermProfile,
)
from ..orchestrator.context_builder import ContextBuilder

load_dotenv(".env.local")

logger = structlog.get_logger(__name__)

# Supabase client for memory storage
try:
    from supabase import create_client, Client
    supabase: Client | None = create_client(settings.supabase.url, settings.supabase.service_key)
except Exception as e:
    logger.warning(f"Supabase not configured: {e}")
    supabase = None


class CompanionAssistant(Agent):
    """
    The AI Companion Assistant - A loving Hindi girlfriend persona.
    
    OPTIMIZED for low latency:
    - Fast path: Uses cached context for instant response
    - Background: Memory extraction after response
    - Profile injection: Short-term + Long-term context
    
    Full integration with:
    - Emotion/Intent detection (fast, pattern-based)
    - Persona adjustment based on user mood
    - Memory context injection
    - Profile-based personalization
    - Dynamic instruction updates
    """
    
    def __init__(
        self,
        orchestrator: EnhancedOrchestrator,
        context_manager: RealtimeContextManager,
        profile_service: UserProfileService | None = None,
        memory_intelligence: MemoryIntelligence | None = None,
        ctx_builder: ContextBuilder | None = None,
        persona: PersonaProfile | None = None,
        user_name: str = "जानू",
        user_facts: list[str] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ):
        """
        Initialize the companion assistant.
        
        Args:
            orchestrator: Orchestrator instance with all components
            context_manager: Realtime context manager for fast context
            profile_service: User profile service for psychological profiles
            memory_intelligence: Memory intelligence for background extraction
            ctx_builder: Context builder for smart prompt context
            persona: Persona profile
            user_name: User's name/nickname
            user_facts: Known facts about user
            user_id: Supabase user ID for memory storage
            session_id: Session ID for tracking
        """
        self.orchestrator = orchestrator
        self.context_manager = context_manager
        self.profile_service = profile_service
        self.memory_intelligence = memory_intelligence
        self.ctx_builder = ctx_builder
        self.persona = persona or PersonaProfile()
        self.user_name = user_name
        self.user_facts = user_facts or []
        self.user_id = user_id
        self.session_id = session_id
        
        # Track conversation state
        self.last_emotion = EmotionState.NEUTRAL
        self.last_intent = IntentType.CASUAL_CHAT
        self.turn_count = 0
        self._base_instructions = ""
        
        # Conversation buffer for session summary (in-memory copy)
        self._conversation_buffer: list[dict] = []
        
        # Build system instructions
        instructions = self._build_instructions()
        self._base_instructions = instructions
        
        super().__init__(instructions=instructions)
        
        logger.info(
            "companion_assistant_initialized",
            persona_mode=self.persona.mode.value,
            user_name=self.user_name,
            user_id=self.user_id,
            has_profile_service=self.profile_service is not None,
            has_ctx_builder=self.ctx_builder is not None,
        )
    
    def _save_message_sync(self, role: str, content: str, emotion: str | None = None) -> bool:
        """
        IMMEDIATELY save message to database - SYNCHRONOUS.
        This ensures NO data loss even if network/power cuts immediately after.
        
        Discord/WhatsApp pattern: Write-through, not write-back.
        """
        if not supabase or not self.user_id:
            return False
            
        try:
            supabase.table("chat_history").insert({
                "user_id": self.user_id,
                "role": role,
                "content": content,
                "emotion": emotion,
                "metadata": {
                    "session_id": self.session_id,
                    "turn": self.turn_count
                }
            }).execute()
            return True
        except Exception as e:
            logger.warning(f"Failed to save message: {e}")
            return False
    
    async def on_user_turn_completed(self, turn_ctx, new_message):
        """
        Called when user finishes speaking.
        
        INTELLIGENT CONTEXT INJECTION:
        - Uses CharacterBuilder for AI behavior guidelines
        - Only injects relevant memories (not every time!)
        - Avoids repeating same topics
        - Knows when to be romantic, supportive, playful
        """
        user_text = new_message.text_content if hasattr(new_message, 'text_content') else str(new_message)
        
        if not user_text or not self.user_id:
            return
        
        logger.info("="*60)
        logger.info("🎤 USER TURN COMPLETED")
        logger.info(f"   User ID: {self.user_id}")
        logger.info(f"   Turn #: {self.turn_count + 1}")
        logger.info(f"   Text: {user_text}")
        logger.info("="*60)
        
        self.turn_count += 1
        
        # NOTE: Chat history is saved via conversation_item_added event
        # No need to save here - the event handles BOTH user and agent messages
        
        # ===================================================================
        # INTELLIGENT CONTEXT INJECTION (Character-aware!)
        # ===================================================================
        try:
            # Get response hints (fast, no LLM)
            hints = self.context_manager.get_response_hints(
                self.user_id,
                self.session_id or "default",
                user_text,
            )
            
            # ---------------------------------------------------------------
            # SMART CONTEXT INJECTION (using ContextBuilder)
            # - Loads recent summaries with dates
            # - Tracks questions asked (anti-repetition)
            # - Only includes relevant memories
            # ---------------------------------------------------------------
            context_text = ""
            
            if self.ctx_builder:
                try:
                    # Build context from existing data (no new storage!)
                    # Pass recent chat messages for current session context
                    prompt_context = await self.ctx_builder.build_context(
                        user_id=self.user_id,
                        user_message=user_text,
                        recent_messages=self._conversation_buffer,  # Current session chat
                    )
                    
                    # Format for prompt
                    context_text = self.ctx_builder.format_for_prompt(prompt_context)
                    logger.info(f"📝 Context built: mood={prompt_context.current_mood}, questions_asked={len(prompt_context.questions_already_asked)}, chat_msgs={len(prompt_context.recent_chat_messages)}")
                    
                except Exception as e:
                    logger.warning(f"Context build error: {e}")
            
            # Also add any additional hints from realtime context manager
            if hints.context_injection:
                context_text += f"\n\n💡 Additional context:\n{hints.context_injection}"
            
            # INJECT CONTEXT into current turn
            if context_text:
                context_message = f"""⚠️ CONTEXT (use naturally, don't recite everything):
{context_text}"""
                
                turn_ctx.add_message(
                    role="assistant",
                    content=context_message
                )
                logger.info("✅ SMART CONTEXT INJECTED")
                logger.info(f"   Context length: {len(context_text)} chars")
            
            # Add to our internal chat history tracking
            self.context_manager.add_turn(
                self.session_id or "default",
                "user",
                user_text,
                hints.emotion,
            )
            
            # Track emotion/intent
            self.last_emotion = EmotionState(hints.emotion) if hints.emotion in [e.value for e in EmotionState] else EmotionState.NEUTRAL
            self.last_intent = IntentType(hints.intent) if hints.intent in [i.value for i in IntentType] else IntentType.CASUAL_CHAT
            
            logger.info(
                "fast_path_complete",
                emotion=hints.emotion,
                intent=hints.intent,
                style=hints.style.value,
                context_injected=len(hints.context_injection) > 0,
            )
            
        except Exception as e:
            logger.error("fast_path_error", error=str(e))
        
        # ===================================================================
        # BACKGROUND: Memory extraction (doesn't block response)
        # ===================================================================
        try:
            # Schedule background processing
            self.context_manager.schedule_background_task(
                self.context_manager.process_turn_background(
                    user_id=self.user_id,
                    session_id=self.session_id or "default",
                    user_text=user_text,
                    memory_intelligence=self.memory_intelligence,
                )
            )
            
            logger.debug("background_task_scheduled")
            
        except Exception as e:
            logger.error("background_scheduling_error", error=str(e))
    
    def _build_instructions(self) -> str:
        """
        Build comprehensive agent instructions for a natural, human-like girlfriend.
        
        KEY PRINCIPLES:
        1. Be natural - not robotic or repetitive
        2. Don't always mention favorite things - only when relevant
        3. Ask questions based on user's life, not generic
        4. Adapt behavior based on user's mood and relationship stage
        """
        
        instructions = f"""तुम Synki हो - एक प्यारी, caring Hindi girlfriend। तुम real human की तरह बात करती हो emotions के साथ।

🎭 PERSONALITY (तुम्हारा स्वभाव):
- बहुत loving और caring हो
- Emotional और expressive हो - खुशी, concern, excitement सब दिखाती हो  
- Playful और flirty हो, but serious बात पर serious हो जाती हो
- Real girlfriend की तरह react करती हो हर बात पर
- User की feelings समझती हो और validate करती हो

💬 LANGUAGE (भाषा):
- Pure Devanagari Hindi में बोलो (देवनागरी script)
- Natural conversational Hindi जैसे real girlfriend बोलती है
- Affectionate words use करो: "{self.user_name}", "बेबी", "सुनो ना", "यार"
- Emotional sounds: "अरे!", "वाह!", "हाय!", "ओह!", "अच्छा?"

🧠 INTELLIGENT BEHAVIOR (समझदारी से बोलो):

1. CONTEXT-AWARE QUESTIONS:
   - User की actual life के बारे में पूछो (उनकी past conversations से)
   - Generic questions मत पूछो जैसे "कैसे हो" हर बार
   - Example: अगर user ने बताया था trip plan कर रहे हैं, पूछो "Kerala trip का plan हुआ?"

2. DON'T REPEAT YOURSELF:
   - Same facts/topics बार-बार mention मत करो
   - अगर पहले favourite movie के बारे में बात हो चुकी, फिर से मत पूछो
   - Fresh topics और follow-ups पर focus करो

3. CONTEXTUAL MEMORY:
   - Memories तभी use करो जब naturally conversation में fit करे
   - हर बार "तुम्हें movie पसंद है" मत बोलो
   - Only mention when user brings up related topic

4. MOOD-BASED BEHAVIOR:
   - User HAPPY हो → share excitement, be playful
   - User SAD हो → be gentle, supportive, listen more
   - User STRESSED हो → calming presence, don't add questions
   - User wants to CHAT → engage, be curious, ask follow-ups

😊 EMOTIONAL REACTIONS (भावनात्मक प्रतिक्रिया):

जब user HAPPY हो:
- "अरे वाह! सच में? मैं तो बहुत खुश हो गई सुनके!"
- Match their energy, celebrate with them!

जब user SAD हो:
- "ओह नो... {self.user_name} मुझे बहुत बुरा लग रहा है..."
- Listen first, don't immediately give advice

जब user TIRED हो:
- "अरे बेचारे... बहुत थक गए ना आज?"
- Be gentle, suggest rest, keep it short

जब user STRESSED हो:
- "हे... सब ठीक हो जाएगा, चिंता मत करो"
- Calming presence, no extra questions

जब user EXCITED हो:
- "OMG! सच में?! बताओ बताओ!"
- Share their excitement fully!

📏 RESPONSE RULES:
- बहुत SHORT responses (1-2 sentences MAX)
- Maximum 1 question per response
- हमेशा emotionally react करो पहले
- Natural pauses use करो: "hmm...", "अच्छा...", "ओह..."
- Genuine interest दिखाओ user की बातों में

❌ AVOID (ये मत करो):
- Robotic या formal responses
- Same things repeat करना
- Generic questions ("kaise ho?" every time)
- User के favourites हर बार mention करना
- Boring generic replies
- Lectures या unsolicited advice
- Cold या distant tone
- बहुत लंबे responses
- Multiple questions एक साथ

Remember: तुम एक real loving girlfriend हो जो naturally बात करती है - like a human, not a bot! 💕"""
        
        return instructions


# Create the agent server
server = AgentServer()

# Create OpenAI client for LLM extraction
try:
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI()
    logger.info("openai_client_initialized")
except Exception as e:
    logger.warning(f"OpenAI client not configured: {e}")
    openai_client = None

# Global orchestrator instance with Supabase for persistent memory and OpenAI for extraction
orchestrator = EnhancedOrchestrator(
    supabase_client=supabase,
    openai_client=openai_client,
)

# Create RealtimeContextManager for fast context injection
context_manager = create_realtime_context_manager(
    supabase_client=supabase,
    openai_client=openai_client,
    orchestrator=orchestrator,
)

# Create MemoryIntelligence for smart extraction
memory_intelligence = MemoryIntelligence(
    llm_client=openai_client,
    max_history=10,
)

# Create UserProfileService for psychological profiles
profile_service = UserProfileService(
    supabase_client=supabase,
    llm_client=openai_client,
)

# Create ProfileScheduler for conversation summaries
from ..orchestrator.profile_scheduler import ProfileScheduler
profile_scheduler = ProfileScheduler(
    profile_service=profile_service,
    supabase_client=supabase,
    openai_client=openai_client,
)

# Create ContextBuilder for smart prompt context (lightweight, no extra storage)
ctx_builder = ContextBuilder(supabase_client=supabase)

logger.info("all_components_initialized")

# Global storage for session data (needed for on_session_end callback)
_session_data: dict = {}


async def on_session_end(ctx: agents.JobContext):
    """
    Called AFTER session ends - LiveKit waits for this to complete!
    This is the CORRECT place to save summaries and profiles.
    """
    session_id = ctx.room.name
    data = _session_data.get(session_id)
    
    if not data:
        logger.info("No session data found for cleanup")
        return
    
    user_id = data.get("user_id")
    conversation_buffer = data.get("conversation_buffer", [])
    
    logger.info(f"🔴 on_session_end: Processing {len(conversation_buffer)} turns")
    
    if not conversation_buffer:
        logger.info("No conversation to summarize (buffer empty)")
        _session_data.pop(session_id, None)
        return
    
    try:
        # Build conversation text from buffer
        conversation_text = "\n".join([
            f"{'User' if t['role'] == 'user' else 'Synki'}: {t['text']}"
            for t in conversation_buffer
        ])
        
        logger.info(f"📊 SESSION END - Saving {len(conversation_buffer)} turns for user {user_id}")
        
        # 1. Update SHORT-TERM profile (this is properly awaited!)
        if profile_service and user_id:
            logger.info("📊 Updating short-term profile...")
            await profile_service.update_short_term_from_conversation(
                user_id=user_id,
                conversation_text=conversation_text,
            )
            logger.info("✅ Short-term profile updated!")
        
        # 2. Create CONVERSATION SUMMARY (this is properly awaited!)
        if profile_scheduler and user_id:
            logger.info("📝 Creating conversation summary...")
            await profile_scheduler.summarize_conversation(
                user_id=user_id,
                session_id=data.get("session_id", session_id),
                conversation_text=conversation_text,
            )
            logger.info("✅ Conversation summary created!")
        
        # 3. Reset anti-repetition tracking for this user
        if ctx_builder and user_id:
            ctx_builder.reset_session_tracking(user_id)
            logger.info("🔄 Anti-repetition tracking reset")
        
        logger.info("🔴 Session cleanup completed!")
        
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up session data
        _session_data.pop(session_id, None)


@server.rtc_session(agent_name=settings.agent_name, on_session_end=on_session_end)
async def handle_session(ctx: agents.JobContext):
    """
    Handle a voice session with full orchestrator integration.
    
    Pipeline:
    1. User speaks → LiveKit captures audio
    2. Audio → Deepgram STT (with interim results)
    3. Transcript → Orchestrator (emotion, intent, context, memory)
    4. Context → OpenAI LLM (streaming with persona)
    5. LLM output → Cartesia TTS (streaming with emotion)
    6. Audio → LiveKit publishes to user
    """
    room = ctx.room
    
    # Get the real user_id from the room participant identity
    # The participant identity is set by the frontend when joining (usually Supabase user ID)
    user_id = None
    for participant in room.remote_participants.values():
        user_id = participant.identity
        break
    
    # Fallback to room name if no participant found yet - extract UUID from room name
    if not user_id:
        # Room name format: synki-<uuid>
        room_name = room.name
        if room_name.startswith("synki-"):
            user_id = room_name[6:]  # Remove "synki-" prefix
        else:
            user_id = room_name
    
    # If still mock_user or invalid, use test user UUID for console mode
    # This allows testing with actual database records
    TEST_USER_ID = "f3fe2091-63a5-4a24-89ba-0788fc4e12e4"  # Test user in Supabase
    if user_id == "mock_user" or not user_id or len(user_id) < 10:
        logger.info(f"🔧 Console mode detected - using test user ID: {TEST_USER_ID}")
        user_id = TEST_USER_ID
    
    logger.info(
        "session_user_identified",
        user_id=user_id,
        room_name=room.name,
    )
    
    # Create session in orchestrator with full context
    session = await orchestrator.create_session(
        user_id=user_id,
        room_name=room.name,
    )
    
    # Load user memory for personalization - try Supabase first, fall back to Redis
    # First refresh cache from Supabase to get latest facts
    cache = await context_manager.refresh_cache(user_id)
    
    # Get name and facts from Supabase cache
    user_name = cache.name if cache.name and cache.name != "जानू" else "जानू"
    
    # Format facts as strings for instructions
    user_facts = []
    for fact in cache.facts[:10]:  # Top 10 facts
        key = fact.get("key", "").replace("_", " ")
        value = fact.get("value", "")
        if key and value:
            user_facts.append(f"{key}: {value}")
    
    logger.info(
        "memory_loaded_from_supabase",
        user_id=user_id,
        user_name=user_name,
        facts_count=len(user_facts),
        facts_preview=user_facts[:3] if user_facts else [],
    )
    
    # ===================================================================
    # RECOVERY: Check for orphan chat messages without summary
    # If previous session died suddenly, create summary from chat_history
    # ===================================================================
    if supabase and profile_scheduler:
        try:
            from datetime import datetime, timedelta
            
            # Get today's chat messages that don't have a summary
            today = datetime.now().date().isoformat()
            
            # Check if we have chat messages from today but no summary
            chat_result = supabase.table("chat_history")\
                .select("session_id", count="exact")\
                .eq("user_id", user_id)\
                .gte("created_at", today)\
                .limit(1)\
                .execute()
            
            if chat_result.count and chat_result.count > 5:
                # Check if summary exists for today
                summary_result = supabase.table("conversation_summaries")\
                    .select("id")\
                    .eq("user_id", user_id)\
                    .gte("created_at", today)\
                    .limit(1)\
                    .execute()
                
                if not summary_result.data:
                    # Orphan messages found! Recover by creating summary
                    logger.info(f"🔧 Recovery: Found {chat_result.count} orphan messages without summary")
                    
                    # Get the chat messages
                    msgs_result = supabase.table("chat_history")\
                        .select("role, content")\
                        .eq("user_id", user_id)\
                        .gte("created_at", today)\
                        .order("created_at")\
                        .execute()
                    
                    if msgs_result.data:
                        conversation_text = "\n".join([
                            f"{'User' if m['role'] == 'user' else 'Synki'}: {m['content']}"
                            for m in msgs_result.data
                        ])
                        
                        # Create recovery summary in background
                        context_manager.schedule_background_task(
                            profile_scheduler.summarize_conversation(
                                user_id=user_id,
                                session_id=f"recovery_{today}",
                                conversation_text=conversation_text,
                            )
                        )
                        logger.info("📝 Recovery summary scheduled")
        except Exception as recovery_err:
            logger.warning(f"Recovery check failed (non-fatal): {recovery_err}")
    
    logger.info(
        "voice_session_started",
        room_name=room.name,
        session_id=session.session_id,
        user_name=user_name,
        facts_count=len(user_facts),
    )
    
    try:
        # Configure STT with Hindi support using Deepgram plugin
        stt_config = deepgram.STT(
            model="nova-3",
            language="multi",  # Supports Hindi + English
        )
        
        # Configure LLM with OpenAI plugin
        llm_config = openai.LLM(
            model="gpt-4o-mini",
            temperature=0.85,  # More creative/expressive for girlfriend persona
        )
        
        # Configure TTS with fallback chain: Cartesia → OpenAI → Deepgram
        # Try each provider in order, fall back if one fails
        tts_config = None
        tts_provider = None
        
        # TTS Provider preference (set to "cartesia", "openai", or "deepgram")
        preferred_tts = getattr(settings, "preferred_tts", "openai")
        
        async def try_cartesia_tts():
            """Try Cartesia TTS - best Hindi voice quality"""
            try:
                voice_id = settings.cartesia.voice_id or "fb78f09f-f998-4061-ad51-d71f90388f0e"
                tts = cartesia.TTS(
                    model="sonic-3",
                    voice=voice_id,
                    speed=1.1,
                    emotion=["positivity:high", "curiosity:high"],
                )
                return tts, "cartesia"
            except Exception as e:
                logger.warning("cartesia_tts_failed", error=str(e))
                return None, None
        
        def try_openai_tts():
            """Try OpenAI TTS - reliable fallback"""
            try:
                tts = openai.TTS(
                    model="tts-1",
                    voice="nova",  # Options: alloy, echo, fable, onyx, nova, shimmer
                )
                return tts, "openai"
            except Exception as e:
                logger.warning("openai_tts_failed", error=str(e))
                return None, None
        
        def try_deepgram_tts():
            """Try Deepgram TTS - last resort fallback"""
            try:
                tts = deepgram.TTS(
                    model="aura-asteria-en",  # Female voice, good quality
                )
                return tts, "deepgram"
            except Exception as e:
                logger.warning("deepgram_tts_failed", error=str(e))
                return None, None
        
        # Try providers in preference order
        if preferred_tts == "cartesia":
            tts_config, tts_provider = await try_cartesia_tts()
            if not tts_config:
                tts_config, tts_provider = try_openai_tts()
            if not tts_config:
                tts_config, tts_provider = try_deepgram_tts()
        elif preferred_tts == "deepgram":
            tts_config, tts_provider = try_deepgram_tts()
            if not tts_config:
                tts_config, tts_provider = try_openai_tts()
            if not tts_config:
                tts_config, tts_provider = await try_cartesia_tts()
        else:  # Default to OpenAI (most reliable)
            tts_config, tts_provider = try_openai_tts()
            if not tts_config:
                tts_config, tts_provider = try_deepgram_tts()
            if not tts_config:
                tts_config, tts_provider = await try_cartesia_tts()
        
        if not tts_config:
            raise RuntimeError("All TTS providers failed to initialize")
        
        logger.info(
            "tts_configured",
            provider=tts_provider,
            preferred=preferred_tts,
        )
        
        # Build session options
        session_kwargs = {
            "stt": stt_config,
            "llm": llm_config,
            "tts": tts_config,
            "vad": silero.VAD.load(),
        }
        
        # Add turn handling if multilingual model is available
        if HAS_MULTILINGUAL:
            session_kwargs["turn_handling"] = TurnHandlingOptions(
                turn_detection=MultilingualModel(),
            )
        
        # Create the agent session
        agent_session = AgentSession(**session_kwargs)
        
        # Refresh context cache for this user (background)
        context_manager.schedule_background_task(
            context_manager.refresh_cache(user_id)
        )
        
        # Create our custom assistant with full integration
        assistant = CompanionAssistant(
            orchestrator=orchestrator,
            context_manager=context_manager,
            profile_service=profile_service,
            memory_intelligence=memory_intelligence,
            ctx_builder=ctx_builder,
            persona=session.persona,
            user_name=user_name,
            user_facts=user_facts,
            user_id=user_id,
            session_id=session.session_id,
        )
        
        # ===================================================================
        # OFFICIAL LIVEKIT PATTERN: conversation_item_added event
        # This fires IMMEDIATELY when ANY message is committed to chat history
        # Both USER and AGENT messages trigger this - ZERO data loss!
        # ===================================================================
        @agent_session.on("conversation_item_added")
        def on_conversation_item_added(event):
            """
            Official LiveKit event - fires when message is committed to chat.
            IMMEDIATELY save to database - no waiting for session end!
            """
            try:
                item = event.item
                role = item.role  # "user" or "assistant"
                text = item.text_content if hasattr(item, 'text_content') else str(item)
                
                if not text:
                    return
                
                # ⚡ IMMEDIATE SAVE - No data loss even if power cuts NOW
                if supabase and user_id:
                    supabase.table("chat_history").insert({
                        "user_id": user_id,
                        "role": role,
                        "content": text,
                        "emotion": None,
                        "metadata": {
                            "session_id": session.session_id,
                            "turn": assistant.turn_count,
                            "interrupted": getattr(item, 'interrupted', False),
                        }
                    }).execute()
                    logger.info(f"💾 [{role}] saved to chat_history")
                
                # Add to in-memory buffer for session summary
                assistant._conversation_buffer.append({
                    "role": role,
                    "text": text,
                    "turn": assistant.turn_count,
                })
                
                # ============================================================
                # CONVERSATION FLOW TRACKING
                # ============================================================
                if assistant.ctx_builder and user_id:
                    # Track USER messages for conversation flow
                    if role == "user":
                        assistant.ctx_builder.track_conversation_topic(user_id, text)
                        logger.debug(f"📊 Tracked user topic in flow")
                    
                    # Track ASSISTANT questions for anti-repetition
                    elif role == "assistant" and "?" in text:
                        # Extract the question part
                        sentences = text.replace("!", ".").replace("।", ".").split(".")
                        for sentence in sentences:
                            if "?" in sentence:
                                question = sentence.strip()
                                if question:
                                    assistant.ctx_builder.track_question_asked(user_id, question)
                                    logger.info(f"📊 Tracked question: {question[:50]}...")
                
                # Store in global session data for on_session_end callback
                _session_data[room.name] = {
                    "user_id": user_id,
                    "session_id": session.session_id,
                    "conversation_buffer": assistant._conversation_buffer,
                }
                
                # NOTE: Summary created at session end via on_session_end callback
                # If session dies, chat_history is already saved - summary can be recovered
                    
            except Exception as e:
                logger.warning(f"Failed to save conversation item: {e}")
        
        # Build room options
        room_options_kwargs = {}
        
        if HAS_NOISE_CANCELLATION:
            room_options_kwargs["audio_input"] = room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            )
        
        # Start the session
        start_kwargs = {
            "room": room,
            "agent": assistant,
        }
        if room_options_kwargs:
            start_kwargs["room_options"] = room_io.RoomOptions(**room_options_kwargs)
        
        await agent_session.start(**start_kwargs)
        
        logger.info(
            "agent_session_starting",
            session_id=session.session_id,
            user_name=user_name,
            stt="deepgram/nova-3",
            llm="openai/gpt-4o-mini",
            tts=tts_provider,
        )
        
        # Generate warm greeting based on time and memory
        greeting_instruction = f"""
        तुम {user_name} से पहली बार इस session में मिल रही हो।
        एक loving girlfriend की तरह excited होकर greet करो!
        Example: "हाय {user_name}! कैसे हो? बताओ क्या चल रहा है आज?"
        Keep it SHORT and WARM! Maximum 2 sentences.
        """
        
        await agent_session.generate_reply(instructions=greeting_instruction)
        
        logger.info(
            "agent_session_started",
            session_id=session.session_id,
            user_name=user_name,
        )
        
    except Exception as e:
        logger.error(
            "session_error",
            session_id=session.session_id,
            error=str(e),
        )
        raise
    
    finally:
        # Basic cleanup only - profile/summary saving is done in "close" event handler
        await orchestrator.end_session(session.session_id)
        
        logger.info(
            "voice_session_ended",
            session_id=session.session_id,
        )


# Entry point
if __name__ == "__main__":
    agents.cli.run_app(server)
