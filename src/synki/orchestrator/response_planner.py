"""
Response Planner

Plans the response strategy before LLM generation.
Decides between cached openers, short responses, or full LLM calls.
"""

import random

import structlog

from ..models import (
    ContextPacket,
    EmotionState,
    IntentType,
    PersonaProfile,
    ResponsePlan,
    ResponseStrategy,
)
from .persona_engine import PersonaEngine

logger = structlog.get_logger(__name__)


class ResponsePlanner:
    """Plans response strategy before LLM generation."""
    
    # Quick responses that don't need LLM
    QUICK_RESPONSES = {
        IntentType.GREETING: {
            EmotionState.NEUTRAL: [
                "hii! kaisa ja raha hai din?",
                "hello! kya chal raha hai?",
                "hiii! kaise ho aaj?",
            ],
            EmotionState.HAPPY: [
                "hiiii! kya baat hai, mood accha lag raha hai!",
                "hello! someone's happy today! bata bata",
            ],
            EmotionState.TIRED: [
                "hii! thake hue lag rahe ho, sab theek?",
                "hello! aaj tired lag rahe ho, kya hua?",
            ],
        },
        IntentType.FAREWELL: {
            EmotionState.NEUTRAL: [
                "bye! take care 💕",
                "accha, chal milte hain! bye",
                "okay bye! baad mein baat karte hain",
            ],
            EmotionState.TIRED: [
                "accha soja jaldi! good night 💕",
                "bye! rest karo properly, okay?",
            ],
        },
    }
    
    # Filler responses for very short user inputs
    ACKNOWLEDGMENTS = [
        "hmm...", "acha...", "I see...", "ohh...", "okay...",
    ]
    
    def __init__(self, persona_engine: PersonaEngine | None = None):
        """
        Initialize response planner.
        
        Args:
            persona_engine: Optional PersonaEngine instance
        """
        self.persona = persona_engine or PersonaEngine()
        self._last_strategy: ResponseStrategy | None = None
    
    def plan(
        self,
        user_text: str,
        intent: IntentType,
        emotion: EmotionState,
        context: ContextPacket,
        recent_responses: list[str] | None = None,
    ) -> ResponsePlan:
        """
        Plan the response strategy.
        
        Args:
            user_text: User's current text
            intent: Detected intent
            emotion: Detected emotion
            context: Current context packet
            recent_responses: Recent assistant responses for anti-repetition
            
        Returns:
            ResponsePlan with strategy and guidelines
        """
        recent = recent_responses or []
        
        # Determine strategy
        strategy = self._select_strategy(user_text, intent, emotion, context)
        
        # Get opener if needed
        use_opener = strategy != ResponseStrategy.CACHED_OPENER
        opener = self.persona.get_opener(emotion) if use_opener else ""
        
        # Determine warmth level
        warmth = self._determine_warmth(emotion, intent)
        
        # Decide on including question
        include_question = self._should_include_question(intent, context)
        
        # Get phrases to avoid (from recent responses)
        avoid_phrases = self._get_avoid_phrases(recent)
        
        # Determine max sentences
        max_sentences = 2 if strategy == ResponseStrategy.SHORT_RESPONSE else 3
        if strategy == ResponseStrategy.EMOTIONAL_RESPONSE:
            max_sentences = 3
        
        plan = ResponsePlan(
            strategy=strategy,
            use_opener=use_opener,
            opener=opener,
            warmth_level=warmth,
            include_question=include_question,
            avoid_phrases=avoid_phrases,
            max_sentences=max_sentences,
        )
        
        self._last_strategy = strategy
        
        logger.info(
            "response_planned",
            strategy=strategy.value,
            warmth=warmth,
            include_question=include_question,
        )
        
        return plan
    
    def get_quick_response(
        self,
        intent: IntentType,
        emotion: EmotionState,
        recent_responses: list[str] | None = None,
    ) -> str | None:
        """
        Get a quick cached response if available.
        
        Args:
            intent: Detected intent
            emotion: Detected emotion
            recent_responses: Recent responses to avoid
            
        Returns:
            Quick response string or None
        """
        recent = recent_responses or []
        
        if intent not in self.QUICK_RESPONSES:
            return None
        
        intent_responses = self.QUICK_RESPONSES[intent]
        responses = intent_responses.get(
            emotion,
            intent_responses.get(EmotionState.NEUTRAL, [])
        )
        
        if not responses:
            return None
        
        # Filter out recently used responses
        available = [r for r in responses if r not in recent[-5:]]
        if not available:
            available = responses
        
        return random.choice(available)
    
    def _select_strategy(
        self,
        user_text: str,
        intent: IntentType,
        emotion: EmotionState,
        context: ContextPacket,
    ) -> ResponseStrategy:
        """Select appropriate response strategy."""
        
        # Very short inputs might just need acknowledgment
        if len(user_text.split()) <= 2:
            if intent == IntentType.GREETING:
                return ResponseStrategy.CACHED_OPENER
            return ResponseStrategy.SHORT_RESPONSE
        
        # Greetings and farewells can use cached responses
        if intent in (IntentType.GREETING, IntentType.FAREWELL):
            return ResponseStrategy.CACHED_OPENER
        
        # Emotional support needs full, empathetic response
        if intent == IntentType.EMOTIONAL_SUPPORT:
            return ResponseStrategy.EMOTIONAL_RESPONSE
        
        # High emotion states need more thoughtful responses
        high_emotion = emotion in (
            EmotionState.SAD,
            EmotionState.STRESSED,
            EmotionState.ANXIOUS,
            EmotionState.ANGRY,
        )
        if high_emotion:
            return ResponseStrategy.EMOTIONAL_RESPONSE
        
        # Playful teasing opportunity
        if self.persona.should_use_teasing(emotion, intent):
            return ResponseStrategy.PLAYFUL_TEASE
        
        # Questions need proper answers
        if intent == IntentType.QUESTION:
            return ResponseStrategy.FULL_RESPONSE
        
        # Default to short response for casual chat
        if intent == IntentType.CASUAL_CHAT:
            # Vary between short and full to keep it natural
            if context.turn_count % 3 == 0:
                return ResponseStrategy.FULL_RESPONSE
            return ResponseStrategy.SHORT_RESPONSE
        
        return ResponseStrategy.FULL_RESPONSE
    
    def _determine_warmth(
        self,
        emotion: EmotionState,
        intent: IntentType,
    ) -> str:
        """Determine appropriate warmth level."""
        
        # High warmth for emotional situations
        if emotion in (EmotionState.SAD, EmotionState.STRESSED, EmotionState.ANXIOUS):
            return "high"
        
        if intent == IntentType.EMOTIONAL_SUPPORT:
            return "high"
        
        # Medium warmth for happy/excited states
        if emotion in (EmotionState.HAPPY, EmotionState.EXCITED):
            return "medium"
        
        # Low warmth for playful/teasing
        if intent == IntentType.CASUAL_CHAT and emotion == EmotionState.NEUTRAL:
            return "medium"
        
        return "medium"
    
    def _should_include_question(
        self,
        intent: IntentType,
        context: ContextPacket,
    ) -> bool:
        """Decide if response should include a question."""
        
        # Don't ask questions in emotional support (let them share)
        if intent == IntentType.EMOTIONAL_SUPPORT:
            return False
        
        # Farewell doesn't need questions
        if intent == IntentType.FAREWELL:
            return False
        
        # Early in conversation, ask more questions
        if context.turn_count < 3:
            return True
        
        # Don't ask too many consecutive questions
        # Check if last response was a question
        if context.recent_assistant_messages:
            last_msg = context.recent_assistant_messages[-1]
            if "?" in last_msg:
                return False
        
        # 40% chance of question in casual chat
        if intent == IntentType.CASUAL_CHAT:
            return random.random() < 0.4
        
        return True
    
    def _get_avoid_phrases(self, recent_responses: list[str]) -> list[str]:
        """Get list of phrases to avoid for anti-repetition."""
        avoid = []
        
        for response in recent_responses[-5:]:
            # Extract first few words
            words = response.split()[:5]
            if words:
                avoid.append(" ".join(words))
        
        return avoid
