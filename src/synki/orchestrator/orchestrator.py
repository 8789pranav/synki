"""
Main Orchestrator

The central coordinator that brings together all orchestrator components
to process user input and generate appropriate responses.
"""

from typing import Any

import structlog

from ..models import (
    ContextPacket,
    EmotionState,
    IntentType,
    LLMInputPacket,
    PersonaProfile,
    ResponsePlan,
    SessionState,
    TranscriptEvent,
)
from .context_manager import ContextManager
from .emotion_detector import EmotionDetector
from .intent_detector import IntentDetector
from .memory_service import MemoryService
from .persona_engine import PersonaEngine
from .response_planner import ResponsePlanner
from .session_manager import SessionManager

logger = structlog.get_logger(__name__)


class Orchestrator:
    """
    Main orchestrator that coordinates all AI components.
    
    Responsibilities:
    - Session management
    - Intent and emotion detection
    - Context management
    - Memory integration
    - Response planning
    - LLM prompt construction
    """
    
    def __init__(
        self,
        redis_client: Any | None = None,
        default_persona: PersonaProfile | None = None,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            redis_client: Optional Redis client for persistence
            default_persona: Default persona profile
        """
        self.session_manager = SessionManager(redis_client)
        self.context_manager = ContextManager()
        self.memory_service = MemoryService(redis_client)
        self.emotion_detector = EmotionDetector()
        self.intent_detector = IntentDetector()
        self.persona_engine = PersonaEngine(default_persona)
        self.response_planner = ResponsePlanner(self.persona_engine)
        
        logger.info("orchestrator_initialized")
    
    async def process_transcript(
        self,
        session_id: str,
        transcript: TranscriptEvent,
    ) -> LLMInputPacket | None:
        """
        Process a transcript event and prepare LLM input.
        
        This is the main entry point for processing user speech.
        
        Args:
            session_id: Session identifier
            transcript: Transcript event from STT
            
        Returns:
            LLMInputPacket if response generation is needed, None otherwise
        """
        # Get session
        session = await self.session_manager.get_session(session_id)
        if not session:
            logger.warning("session_not_found", session_id=session_id)
            return None
        
        text = transcript.text.strip()
        if not text:
            return None
        
        # For interim results, just detect early patterns
        if not transcript.is_final:
            return await self._process_interim(session, text)
        
        # Full processing for final transcripts
        return await self._process_final(session, text)
    
    async def _process_interim(
        self,
        session: SessionState,
        text: str,
    ) -> LLMInputPacket | None:
        """
        Process interim transcript for early pattern detection.
        
        Used for fast-path responses like quick openers.
        """
        # Early intent detection for fast responses
        intent, confidence = self.intent_detector.detect(text)
        
        # High-confidence greeting can trigger quick response
        if intent == IntentType.GREETING and confidence > 0.6:
            emotion, _ = self.emotion_detector.detect(text)
            quick_response = self.response_planner.get_quick_response(
                intent, emotion, session.recent_phrases
            )
            if quick_response:
                logger.info(
                    "fast_path_triggered",
                    intent=intent.value,
                    response_preview=quick_response[:30],
                )
                # Return a minimal packet for quick response
                return LLMInputPacket(
                    persona_mode=session.persona.mode,
                    style="quick_response",
                    user_text=text,
                    response_goal=quick_response,  # Pre-generated response
                )
        
        return None
    
    async def _process_final(
        self,
        session: SessionState,
        text: str,
    ) -> LLMInputPacket:
        """
        Process final transcript and build full LLM input.
        """
        # Detect intent and emotion
        intent, intent_confidence = self.intent_detector.detect(text)
        emotion, emotion_confidence = self.emotion_detector.detect(text)
        
        logger.info(
            "input_analyzed",
            intent=intent.value,
            emotion=emotion.value,
            text_preview=text[:50],
        )
        
        # Build context packet
        context = self.context_manager.build_context_packet(
            session, text, emotion, intent
        )
        
        # Get long-term memory
        memory = await self.memory_service.get_memory(session.user_id)
        memory_facts = self.memory_service.get_memory_facts(memory)
        
        # Learn from this conversation
        await self.memory_service.learn_from_conversation(
            session.user_id, text, context.current_topic
        )
        
        # Plan response strategy
        plan = self.response_planner.plan(
            text, intent, emotion, context, session.recent_phrases
        )
        
        # Check for quick response opportunity
        if plan.strategy.value == "cached_opener":
            quick = self.response_planner.get_quick_response(
                intent, emotion, session.recent_phrases
            )
            if quick:
                return LLMInputPacket(
                    persona_mode=session.persona.mode,
                    style="quick_response",
                    user_text=text,
                    response_goal=quick,
                    emotion=emotion,
                    strategy=plan.strategy,
                )
        
        # Build full LLM input packet
        llm_packet = self._build_llm_packet(
            session=session,
            text=text,
            intent=intent,
            emotion=emotion,
            context=context,
            plan=plan,
            memory_facts=memory_facts,
        )
        
        # Update session context
        await self.session_manager.update_context(
            session.session_id,
            user_message=text,
        )
        
        return llm_packet
    
    def _build_llm_packet(
        self,
        session: SessionState,
        text: str,
        intent: IntentType,
        emotion: EmotionState,
        context: ContextPacket,
        plan: ResponsePlan,
        memory_facts: list[str],
    ) -> LLMInputPacket:
        """Build the LLM input packet."""
        
        # Get compact history for context
        history = self.context_manager.get_compact_history(context, max_items=3)
        
        # Build response goal
        response_goal = self.persona_engine.format_response_goal(
            intent, emotion, plan.include_question
        )
        
        # Add plan-specific instructions
        if plan.opener:
            response_goal = f"Start with '{plan.opener}'. {response_goal}"
        
        if plan.avoid_phrases:
            avoid_str = ", ".join(f"'{p}'" for p in plan.avoid_phrases[:3])
            response_goal += f" Avoid starting with: {avoid_str}"
        
        return LLMInputPacket(
            persona_mode=session.persona.mode,
            style=f"{plan.warmth_level} warmth, {session.persona.language_style.value}",
            user_text=text,
            recent_context=history,
            memory_facts=memory_facts,
            response_goal=response_goal,
            emotion=emotion,
            strategy=plan.strategy,
        )
    
    async def handle_response_generated(
        self,
        session_id: str,
        response_text: str,
    ) -> None:
        """
        Handle post-generation tasks.
        
        Args:
            session_id: Session identifier
            response_text: Generated response text
        """
        # Update session with assistant message
        await self.session_manager.update_context(
            session_id,
            assistant_message=response_text,
        )
        
        logger.debug(
            "response_recorded",
            session_id=session_id,
            response_preview=response_text[:50],
        )
    
    async def create_session(
        self,
        user_id: str,
        room_name: str,
        persona: PersonaProfile | None = None,
    ) -> SessionState:
        """
        Create a new conversation session.
        
        Args:
            user_id: User identifier
            room_name: LiveKit room name
            persona: Optional persona override
            
        Returns:
            New SessionState
        """
        return await self.session_manager.create_session(
            user_id, room_name, persona
        )
    
    async def end_session(self, session_id: str) -> None:
        """End a conversation session."""
        await self.session_manager.end_session(session_id)
    
    def get_system_prompt(
        self,
        session: SessionState,
        user_emotion: EmotionState = EmotionState.NEUTRAL,
        memory_facts: list[str] | None = None,
    ) -> str:
        """
        Get the system prompt for LLM.
        
        Args:
            session: Current session state
            user_emotion: Detected user emotion
            memory_facts: Optional memory facts
            
        Returns:
            System prompt string
        """
        # Get user name from memory if available
        user_name = None
        if hasattr(session, 'user_id'):
            # Would typically look up from memory
            pass
        
        return self.persona_engine.get_system_prompt(
            user_name=user_name,
            user_emotion=user_emotion,
            memory_facts=memory_facts,
        )
