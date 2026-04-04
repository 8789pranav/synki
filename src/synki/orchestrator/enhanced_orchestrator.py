"""
Enhanced Orchestrator

The central coordinator that brings together all orchestrator components
including the layered memory system, entity extraction, thread management,
and anti-repetition.
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

# New layered memory components
from .layered_memory import (
    LayeredMemoryService,
    Entity,
    EntityType,
    MemoryFact,
    MemoryCategory,
    ThreadType,
)
from .entity_extractor import EntityExtractor
from .thread_manager import ThreadManager
from .anti_repetition import AntiRepetitionChecker
from .summary_generator import SummaryGenerator
from .proactive_memory import ProactiveMemoryPrompter, MemoryPrompt

# Memory Intelligence System
from .memory_intelligence import (
    MemoryIntelligence,
    ConversationMemoryManager,
)

logger = structlog.get_logger(__name__)


class EnhancedOrchestrator:
    """
    Enhanced orchestrator with full layered memory support.
    
    Implements the 6-layer memory architecture:
    - L0: Realtime turn buffer
    - L1: Short-term session memory
    - L2: Thread memory
    - L3: Long-term profile memory
    - L4: Semantic recall
    - L5: Anti-repetition memory
    - L6: Summaries and events
    
    Plus: Memory Intelligence for smart extraction and context injection
    """
    
    def __init__(
        self,
        redis_client: Any | None = None,
        supabase_client: Any | None = None,
        openai_client: Any | None = None,
        default_persona: PersonaProfile | None = None,
    ):
        """
        Initialize the enhanced orchestrator.
        
        Args:
            redis_client: Redis client for L0/L1/L5
            supabase_client: Supabase client for L2/L3/L4/L6
            openai_client: OpenAI client for embeddings and extraction
            default_persona: Default persona profile
        """
        # Original components
        self.session_manager = SessionManager(redis_client)
        self.context_manager = ContextManager()
        self.memory_service = MemoryService(redis_client)
        self.emotion_detector = EmotionDetector()
        self.intent_detector = IntentDetector()
        self.persona_engine = PersonaEngine(default_persona)
        self.response_planner = ResponsePlanner(self.persona_engine)
        
        # New layered memory components
        self.layered_memory = LayeredMemoryService(
            redis_client=redis_client,
            supabase_client=supabase_client,
            openai_client=openai_client,
        )
        self.entity_extractor = EntityExtractor(llm_client=openai_client)
        self.thread_manager = ThreadManager(supabase_client=supabase_client)
        self.anti_repetition = AntiRepetitionChecker(
            redis_client=redis_client,
            supabase_client=supabase_client,
        )
        self.summary_generator = SummaryGenerator(
            llm_client=openai_client,
            supabase_client=supabase_client,
        )
        self.proactive_memory = ProactiveMemoryPrompter(
            supabase_client=supabase_client,
        )
        
        # Memory Intelligence System - smart extraction with chat history
        self.memory_intelligence = MemoryIntelligence(
            llm_client=openai_client,
            max_history=10,
        )
        self.memory_manager = ConversationMemoryManager(
            memory_intelligence=self.memory_intelligence,
            supabase_client=supabase_client,
        ) if openai_client else None
        
        self._supabase = supabase_client
        self._openai = openai_client
        
        # Track pending memory questions per session
        self._pending_memory_prompts: dict[str, MemoryPrompt | None] = {}
        
        logger.info("enhanced_orchestrator_initialized")
    
    async def process_transcript(
        self,
        session_id: str,
        transcript: TranscriptEvent,
    ) -> LLMInputPacket | None:
        """
        Process a transcript event with full memory integration.
        
        This is the main entry point for processing user speech.
        """
        # Get session
        session = await self.session_manager.get_session(session_id)
        if not session:
            logger.warning("session_not_found", session_id=session_id)
            return None
        
        text = transcript.text.strip()
        if not text:
            return None
        
        # Update turn buffer (L0)
        if not transcript.is_final:
            self.layered_memory.add_transcript_fragment(session_id, text)
            return await self._process_interim(session, text)
        
        # Finalize turn and process
        complete_text = self.layered_memory.finalize_user_turn(session_id)
        text = complete_text or text
        
        return await self._process_final_enhanced(session, text)
    
    async def _process_interim(
        self,
        session: SessionState,
        text: str,
    ) -> LLMInputPacket | None:
        """Process interim transcript for early pattern detection."""
        intent, confidence = self.intent_detector.detect(text)
        
        # High-confidence greeting can trigger quick response
        if intent == IntentType.GREETING and confidence > 0.6:
            emotion, _ = self.emotion_detector.detect(text)
            
            # Get fresh opener using anti-repetition
            opener = self.anti_repetition.get_fresh_opener(
                session.session_id,
                emotion=emotion.value
            )
            
            if opener:
                logger.info(
                    "fast_path_triggered",
                    intent=intent.value,
                    opener=opener[:30],
                )
                return LLMInputPacket(
                    persona_mode=session.persona.mode,
                    style="quick_response",
                    user_text=text,
                    response_goal=opener,
                )
        
        return None
    
    async def _process_final_enhanced(
        self,
        session: SessionState,
        text: str,
    ) -> LLMInputPacket:
        """
        Process final transcript with full layered memory integration.
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
        
        # Extract entities from the message
        entities = self.entity_extractor.extract_entities(text)
        facts = self.entity_extractor.extract_memory_facts(text)
        
        # Check for entity references that need resolution
        entity_refs = self.entity_extractor.detect_entity_references(text)
        resolved_entities = {}
        
        for entity_type, _ in entity_refs:
            resolved = await self.layered_memory.resolve_entity_reference(
                session.user_id,
                entity_type,
                session.session_id,
                hours_back=48
            )
            if resolved:
                resolved_entities[entity_type.value] = resolved
                logger.info(
                    "entity_resolved",
                    type=entity_type.value,
                    value=resolved.value
                )
        
        # Update session state with entities (L1)
        for entity in entities:
            await self.layered_memory.add_entity_to_session(
                session.user_id, session.session_id, entity
            )
        
        # Detect or continue thread (L2)
        active_thread = await self.thread_manager.detect_thread_continuation(
            text, session.user_id, entities
        )
        
        if not active_thread:
            thread_type = await self.thread_manager.detect_thread_type(text, entities)
            if thread_type:
                # Create new thread
                title = self._generate_thread_title(text, thread_type, entities)
                active_thread = await self.thread_manager.get_or_create_thread(
                    session.user_id, thread_type, title, entities
                )
        else:
            # Update existing thread with new entities
            for entity in entities:
                await self.thread_manager.add_entity_to_thread(
                    active_thread.id, entity
                )
        
        # Save memory facts (L3)
        for fact in facts:
            await self.layered_memory.save_memory_fact(session.user_id, fact)
        
        # Get full context from layered memory
        memory_context = await self.layered_memory.retrieve_context_for_response(
            user_id=session.user_id,
            session_id=session.session_id,
            current_message=text,
            detected_emotion=emotion.value,
            detected_entities=entities
        )
        
        # Build context packet
        context = self.context_manager.build_context_packet(
            session, text, emotion, intent
        )
        
        # Get legacy memory for backward compatibility
        memory = await self.memory_service.get_memory(session.user_id)
        memory_facts_legacy = self.memory_service.get_memory_facts(memory)
        
        # Plan response strategy
        plan = self.response_planner.plan(
            text, intent, emotion, context, session.recent_phrases
        )
        
        # Apply anti-repetition to opener
        if plan.opener:
            if self.anti_repetition.is_phrase_repetitive(
                session.session_id, plan.opener
            ):
                plan.opener = self.anti_repetition.get_fresh_opener(
                    session.session_id, emotion.value
                )
        
        # Check for proactive memory prompts (medicine, birthday, etc.)
        session_state = await self.layered_memory.get_session_state(
            session.user_id, session.session_id
        )
        memory_prompt = self.proactive_memory.analyze_for_memory_prompts(
            text,
            session.session_id,
            session_state.recent_messages
        )
        
        # Check if user is responding to a previous memory question
        pending_response = self.proactive_memory._check_pending_response(
            text, session.session_id
        )
        if pending_response:
            # Save the collected memory
            await self.proactive_memory.save_collected_memory(
                session.user_id,
                pending_response,
                self.layered_memory
            )
            logger.info(
                "proactive_memory_collected",
                topic=pending_response.topic.value,
                field=pending_response.missing_field,
                answer=pending_response.context.get("answer")
            )
        
        # Store pending prompt for inclusion in response
        self._pending_memory_prompts[session.session_id] = memory_prompt
        
        # Build enhanced LLM packet
        llm_packet = self._build_enhanced_llm_packet(
            session=session,
            text=text,
            intent=intent,
            emotion=emotion,
            context=context,
            plan=plan,
            memory_facts=memory_facts_legacy,
            memory_context=memory_context,
            active_thread=active_thread,
            resolved_entities=resolved_entities,
        )
        
        # Update session state (L1)
        await self.layered_memory.add_message_to_session(
            session.user_id,
            session.session_id,
            "user",
            text,
            emotion.value
        )
        
        await self.layered_memory.update_session_emotion(
            session.user_id, session.session_id, emotion.value
        )
        
        # Update legacy session
        await self.session_manager.update_context(
            session.session_id,
            user_message=text,
        )
        
        # Clear turn buffer for next turn
        self.layered_memory.clear_turn_buffer(session.session_id)
        
        return llm_packet
    
    def _build_enhanced_llm_packet(
        self,
        session: SessionState,
        text: str,
        intent: IntentType,
        emotion: EmotionState,
        context: ContextPacket,
        plan: ResponsePlan,
        memory_facts: list[str],
        memory_context: dict,
        active_thread: Any | None = None,
        resolved_entities: dict | None = None,
    ) -> LLMInputPacket:
        """Build enhanced LLM input packet with layered memory context."""
        
        # Get compact history
        history = self.context_manager.get_compact_history(context, max_items=3)
        
        # Build response goal
        response_goal = self.persona_engine.format_response_goal(
            intent, emotion, plan.include_question
        )
        
        # Add opener instruction
        if plan.opener:
            response_goal = f"Start naturally with something like '{plan.opener}'. {response_goal}"
        
        # Add avoid phrases
        if plan.avoid_phrases:
            avoid_str = ", ".join(f"'{p}'" for p in plan.avoid_phrases[:3])
            response_goal += f" Avoid starting with: {avoid_str}"
        
        # Add thread context
        if active_thread:
            thread_context = (
                f"\nActive thread: {active_thread.thread_type.value} - {active_thread.title}"
            )
            if active_thread.summary:
                thread_context += f"\nThread summary: {active_thread.summary}"
            if active_thread.pending_followup:
                thread_context += f"\nPending followup: {active_thread.pending_followup}"
            
            response_goal += thread_context
        
        # Add resolved entity context
        if resolved_entities:
            for entity_type, entity in resolved_entities.items():
                response_goal += f"\nNote: 'that {entity_type}' refers to '{entity.value}'"
        
        # Add relevant facts from memory
        relevant_facts = memory_context.get("relevant_facts", [])
        if relevant_facts:
            facts_str = ", ".join([
                f"{f.fact_key}: {f.fact_value}" for f in relevant_facts[:5]
            ])
            memory_facts.append(f"Known facts: {facts_str}")
        
        # Add upcoming events context
        events = memory_context.get("upcoming_events", [])
        if events:
            event_str = ", ".join([
                f"{e.get('event_title', '')} on {e.get('event_date', '')}"
                for e in events[:3]
            ])
            memory_facts.append(f"Upcoming: {event_str}")
        
        # Add anti-repetition hints
        recent_patterns = memory_context.get("recent_patterns", {})
        if recent_patterns.get("openers"):
            response_goal += f"\nDon't start with: {', '.join(recent_patterns['openers'][-3:])}"
        
        # Add proactive memory question if pending
        pending_prompt = self._pending_memory_prompts.get(session.session_id)
        if pending_prompt:
            question = self.proactive_memory.format_question_for_response(pending_prompt)
            response_goal += f"\nIMPORTANT: End your response by asking: {question}"
        
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
        Handle post-generation tasks with memory updates.
        """
        session = await self.session_manager.get_session(session_id)
        if not session:
            return
        
        # Update layered memory (L1)
        await self.layered_memory.add_message_to_session(
            session.user_id,
            session_id,
            "assistant",
            response_text
        )
        
        # Track phrases for anti-repetition (L5)
        self.anti_repetition.track_phrase_usage(session_id, response_text[:50])
        
        # Update legacy session
        await self.session_manager.update_context(
            session_id,
            assistant_message=response_text,
        )
        
        # Store embedding for semantic recall (L4)
        await self.layered_memory.store_embedding(
            session.user_id,
            "conversation",
            response_text,
            session_id
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
        """Create a new conversation session."""
        session = await self.session_manager.create_session(
            user_id, room_name, persona
        )
        
        # Initialize layered memory session state (L1)
        await self.layered_memory.get_session_state(user_id, session.session_id)
        
        return session
    
    async def end_session(self, session_id: str) -> None:
        """End a conversation session with summary generation."""
        session = await self.session_manager.get_session(session_id)
        if session:
            # Get session messages for summary
            session_state = await self.layered_memory.get_session_state(
                session.user_id, session_id
            )
            
            if session_state.recent_messages:
                # Generate session summary (L6)
                summary = await self.summary_generator.generate_session_summary(
                    user_id=session.user_id,
                    session_id=session_id,
                    messages=session_state.recent_messages,
                )
                
                if summary.get("summary_text"):
                    await self.summary_generator.save_session_summary(
                        session.user_id, session_id, summary
                    )
            
            # Clear anti-repetition tracking
            self.anti_repetition.clear_session(session_id)
        
        await self.session_manager.end_session(session_id)
    
    def get_system_prompt(
        self,
        session: SessionState,
        user_emotion: EmotionState = EmotionState.NEUTRAL,
        memory_facts: list[str] | None = None,
    ) -> str:
        """Get the system prompt for LLM."""
        user_name = None
        return self.persona_engine.get_system_prompt(
            user_name=user_name,
            user_emotion=user_emotion,
            memory_facts=memory_facts,
        )
    
    def _generate_thread_title(
        self,
        text: str,
        thread_type: ThreadType,
        entities: list[Entity]
    ) -> str:
        """Generate a title for a new thread."""
        if entities:
            main_entity = entities[0]
            return f"{thread_type.value}: {main_entity.value}"
        
        # Extract key words from text
        words = text.split()[:5]
        return f"{thread_type.value}: {' '.join(words)}..."


# Factory function to create appropriate orchestrator
def create_orchestrator(
    redis_client: Any | None = None,
    supabase_client: Any | None = None,
    openai_client: Any | None = None,
    default_persona: PersonaProfile | None = None,
    use_enhanced: bool = True,
) -> Any:
    """
    Factory to create orchestrator instance.
    
    Args:
        redis_client: Redis client
        supabase_client: Supabase client
        openai_client: OpenAI client
        default_persona: Default persona
        use_enhanced: Whether to use enhanced orchestrator with layered memory
        
    Returns:
        Orchestrator or EnhancedOrchestrator instance
    """
    if use_enhanced and (supabase_client or openai_client):
        return EnhancedOrchestrator(
            redis_client=redis_client,
            supabase_client=supabase_client,
            openai_client=openai_client,
            default_persona=default_persona,
        )
    
    # Import original for backward compatibility
    from .orchestrator import Orchestrator
    return Orchestrator(
        redis_client=redis_client,
        default_persona=default_persona,
    )
