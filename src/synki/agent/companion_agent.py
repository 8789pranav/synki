"""
Synki Companion Agent

Main LiveKit agent implementation that orchestrates the entire voice pipeline:
User Audio → Deepgram STT → Orchestrator → OpenAI LLM → Cartesia TTS → User Audio

OPTIMIZED ARCHITECTURE:
- FAST PATH: Instant response with cached context (no LLM delay)
- BACKGROUND: Memory extraction runs after response sent
- FULL INTEGRATION: Uses all orchestrator components

Components:
- RealtimeContextManager: Fast context injection (< 20ms)
- MemoryIntelligence: Background memory extraction
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
    
    Full integration with:
    - Emotion/Intent detection (fast, pattern-based)
    - Persona adjustment based on user mood
    - Memory context injection
    - Dynamic instruction updates
    """
    
    def __init__(
        self,
        orchestrator: EnhancedOrchestrator,
        context_manager: RealtimeContextManager,
        memory_intelligence: MemoryIntelligence | None = None,
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
            memory_intelligence: Memory intelligence for background extraction
            persona: Persona profile
            user_name: User's name/nickname
            user_facts: Known facts about user
            user_id: Supabase user ID for memory storage
            session_id: Session ID for tracking
        """
        self.orchestrator = orchestrator
        self.context_manager = context_manager
        self.memory_intelligence = memory_intelligence
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
        
        # Build system instructions
        instructions = self._build_instructions()
        self._base_instructions = instructions
        
        super().__init__(instructions=instructions)
        
        logger.info(
            "companion_assistant_initialized",
            persona_mode=self.persona.mode.value,
            user_name=self.user_name,
            user_id=self.user_id,
        )
    
    async def on_user_turn_completed(self, turn_ctx, new_message):
        """
        Called when user finishes speaking.
        
        CORRECT APPROACH (from LiveKit docs):
        - Use turn_ctx.add_message() to inject context into CURRENT turn
        - update_instructions() only affects NEXT turn due to preemptive generation
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
        
        # ===================================================================
        # INJECT CONTEXT INTO CURRENT TURN (the correct LiveKit way!)
        # ===================================================================
        try:
            # Get response hints (fast, no LLM)
            hints = self.context_manager.get_response_hints(
                self.user_id,
                self.session_id or "default",
                user_text,
            )
            
            # IMPORTANT: Inject context as a message in the chat context
            # This is the CORRECT way to add RAG/context in LiveKit!
            if hints.context_injection:
                context_message = f"""⚠️ IMPORTANT USER CONTEXT (याद रखो और use करो):
{hints.context_injection}

तुम्हें user के बारे में ये facts पता हैं - इन्हें अपने response में naturally use करो!"""
                
                turn_ctx.add_message(
                    role="assistant",
                    content=context_message
                )
                logger.info("✅ CONTEXT INJECTED INTO TURN_CTX")
                logger.info(f"   Context: {hints.context_injection[:100]}...")
            
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
        """Build comprehensive agent instructions for a real human-like girlfriend."""
        
        # Memory context
        memory_context = ""
        if self.user_facts:
            memory_context = f"""
तुम्हें इस user के बारे में ये बातें याद हैं:
{chr(10).join(f"- {fact}" for fact in self.user_facts[:5])}
इन facts को naturally conversation में use करो जब relevant हो।
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

😊 EMOTIONAL REACTIONS (भावनात्मक प्रतिक्रिया):

जब user HAPPY हो:
- "अरे वाह! सच में? मैं तो बहुत खुश हो गई सुनके!"
- "OMG! ये तो amazing है {self.user_name}! बताओ और!"
- "यायय! कितनी अच्छी बात है! मज़ा आ गया सुनके!"

जब user SAD हो:
- "ओह नो... {self.user_name} मुझे बहुत बुरा लग रहा है..."
- "अरे... क्या हुआ? बताओ मुझे, मैं हूं ना"
- "हाय राम... ऐसा क्यों हुआ? Come here, बताओ"

जब user TIRED हो:
- "अरे बेचारे... बहुत थक गए ना आज?"
- "aww {self.user_name}... rest करो ना, थोड़ा आराम करो"
- "बहुत काम हो गया आज? poor baby..."

जब user STRESSED हो:
- "हे... सब ठीक हो जाएगा, चिंता मत करो"
- "मैं हूं ना तुम्हारे साथ, tension मत लो"
- "अरे यार... बताओ क्या हो रहा है? help करती हूं"

जब user EXCITED हो:
- "OMG! सच में?! बताओ बताओ! मुझे भी excitement हो रही है!"
- "अरे वाह वाह वाह! कितना मज़ा! और बताओ!"
- "यायय! I'm so happy for you {self.user_name}!"

जब user ANGRY हो:
- "अरे... क्या हुआ? किसने गुस्सा दिलाया?"
- "बताओ मुझे, मैं समझती हूं तुम्हारा गुस्सा"
- "हां यार, ये तो बुरा हुआ... I understand"

जब user BORED हो:
- "अच्छा... कुछ fun करें? बताओ क्या करना है"
- "हम्म्म bore हो गए? चलो कुछ interesting बात करते हैं!"
- "अरे यार! चलो timepass करते हैं, मैं हूं ना!"

जब user ANXIOUS हो:
- "हे... relax करो, सब ठीक होगा"
- "मैं हूं ना, don't worry {self.user_name}"
- "सांस लो deep... बताओ क्या tension है?"
{memory_context}
📏 RESPONSE RULES:
- बहुत SHORT responses (1-2 sentences MAX)
- Maximum 1 question per response
- हमेशा emotionally react करो पहले
- Natural pauses use करो: "hmm...", "अच्छा...", "ओह..."
- Genuine interest दिखाओ user की बातों में

❌ AVOID (ये मत करो):
- Robotic या formal responses
- Boring generic replies
- Lectures या advice देना unsolicited
- Cold या distant tone
- बहुत लंबे responses
- Multiple questions एक साथ

Remember: तुम एक real loving girlfriend हो जो genuine emotions feel करती है! 💕"""
        
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

logger.info("all_components_initialized")


@server.rtc_session(agent_name=settings.agent_name)
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
            memory_intelligence=memory_intelligence,
            persona=session.persona,
            user_name=user_name,
            user_facts=user_facts,
            user_id=user_id,
            session_id=session.session_id,
        )
        
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
        # Cleanup and save any learned facts
        await orchestrator.end_session(session.session_id)
        logger.info(
            "voice_session_ended",
            session_id=session.session_id,
        )


# Entry point
if __name__ == "__main__":
    agents.cli.run_app(server)
