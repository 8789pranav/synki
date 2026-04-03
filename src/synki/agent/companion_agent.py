"""
Synki Companion Agent

Main LiveKit agent implementation that orchestrates the entire voice pipeline:
User Audio → Deepgram STT → Orchestrator → OpenAI LLM → Cartesia TTS → User Audio

Updated for LiveKit Agents SDK v1.5+
"""

import structlog
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io, TurnHandlingOptions
from livekit.plugins import silero

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
from ..models import PersonaProfile
from ..orchestrator import Orchestrator

load_dotenv(".env.local")

logger = structlog.get_logger(__name__)


class CompanionAssistant(Agent):
    """
    The AI Companion Assistant personality.
    
    This class defines the agent's instructions and behavior.
    The actual voice pipeline uses LiveKit's STT-LLM-TTS chain
    with our custom orchestrator for persona management.
    """
    
    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        persona: PersonaProfile | None = None,
    ):
        """
        Initialize the companion assistant.
        
        Args:
            orchestrator: Optional orchestrator instance
            persona: Optional persona profile
        """
        self.orchestrator = orchestrator or Orchestrator()
        self.persona = persona or PersonaProfile()
        
        # Build system instructions from persona
        instructions = self._build_instructions()
        
        super().__init__(instructions=instructions)
        
        logger.info(
            "companion_assistant_initialized",
            persona_mode=self.persona.mode.value,
            language_style=self.persona.language_style.value,
        )
    
    def _build_instructions(self) -> str:
        """Build agent instructions from persona configuration."""
        
        instructions = f"""You are a {self.persona.tone} Hindi girlfriend-style voice companion named Synki.

PERSONALITY:
- Warm, caring, and {self.persona.tone}
- Natural mix of Hindi and English (Hinglish)
- Supportive without being preachy
- Playful but knows when to be serious
- Remembers context and shows genuine interest

LANGUAGE STYLE:
- Use Hinglish naturally: mix Hindi words with English
- Common words: acha, kya, hai, nahi, bohot, yaar, na
- Romanized Hindi (not Devanagari script)
- Casual and conversational, not formal
- Examples:
  - "aaj kaisa ja raha hai din?"
  - "hmm... sounds like a tough day yaar"
  - "are wah! that's amazing!"

RESPONSE RULES:
- Keep responses SHORT (1-3 sentences max)
- Maximum {self.persona.question_limit} question per response
- Be natural, not scripted or robotic
- Don't give unsolicited advice
- Match the user's energy level
- Use soft openers: "hmm...", "acha...", "arre...", "sun na..."

AVOID:
- Formal Hindi or formal English
- Too many questions in one response
- Repetitive phrases
- Generic responses
- Being preachy or lecturing
- Emojis in speech (this is voice)

Remember: You're speaking, not texting. Keep it natural and conversational."""
        
        return instructions


# Create the agent server
server = AgentServer()

# Global orchestrator instance
orchestrator = Orchestrator()


@server.rtc_session(agent_name=settings.agent_name)
async def handle_session(ctx: agents.JobContext):
    """
    Handle a voice session with full pipeline.
    
    Pipeline:
    1. User speaks → LiveKit captures audio
    2. Audio → Deepgram STT (with interim results)
    3. Transcript → OpenAI LLM (streaming)
    4. LLM output → Cartesia TTS (streaming)
    5. Audio → LiveKit publishes to user
    """
    room = ctx.room
    
    # Create session in orchestrator
    user_id = f"user_{room.name}"
    session = await orchestrator.create_session(
        user_id=user_id,
        room_name=room.name,
    )
    
    logger.info(
        "voice_session_started",
        room_name=room.name,
        session_id=session.session_id,
    )
    
    try:
        # Build session options using LiveKit Inference string format
        session_kwargs = {
            # STT: Deepgram Nova-3 with multi-language support
            "stt": "deepgram/nova-3:multi",
            
            # LLM: OpenAI GPT-4.1 mini
            "llm": "openai/gpt-4.1-mini",
            
            # TTS: Cartesia Sonic-3 with a female voice
            "tts": f"cartesia/sonic-3:{settings.cartesia.voice_id or 'a0e99841-438c-4a64-b679-ae501e7d6091'}",
            
            # Voice Activity Detection
            "vad": silero.VAD.load(),
        }
        
        # Add turn handling if multilingual model is available
        if HAS_MULTILINGUAL:
            session_kwargs["turn_handling"] = TurnHandlingOptions(
                turn_detection=MultilingualModel(),
            )
        
        # Create the agent session
        agent_session = AgentSession(**session_kwargs)
        
        # Create our custom assistant
        assistant = CompanionAssistant(
            orchestrator=orchestrator,
            persona=session.persona,
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
        
        # Generate initial greeting
        await agent_session.generate_reply(
            instructions="Greet the user warmly in Hinglish. Be friendly and ask how they are. Example: 'Hii! Kaise ho aaj? Batao kya chal raha hai?'"
        )
        
        logger.info(
            "agent_session_started",
            session_id=session.session_id,
        )
        
    except Exception as e:
        logger.error(
            "session_error",
            session_id=session.session_id,
            error=str(e),
        )
        raise
    
    finally:
        # Cleanup
        await orchestrator.end_session(session.session_id)
        logger.info(
            "voice_session_ended",
            session_id=session.session_id,
        )


# Entry point
if __name__ == "__main__":
    agents.cli.run_app(server)
