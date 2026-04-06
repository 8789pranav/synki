"""
Response Planner

Plans the response strategy before LLM generation.
Decides between cached openers, short responses, or full LLM calls.
"""

import random
from datetime import datetime

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


# ============================================================================
# PERSONA-SPECIFIC GREETINGS (not generic!)
# ============================================================================

PERSONA_GREETINGS = {
    "CHILL": {
        "morning": ["yo", "morning", "haan bolo", "sup"],
        "afternoon": ["haan", "bolo", "yo", "kya"],
        "evening": ["haan bolo", "yo", "kya scene"],
        "night": ["haan", "bolo", "hmm"],
    },
    "PLAYFUL": {
        "morning": ["ohooo! subah subah yaad aaya 😏", "arre hero! itni jaldi? 😂", "good morning sunshine 🤭"],
        "afternoon": ["ohooo! kya chal raha hai scene? 😏", "arey arey! kaun hai ye? 😂", "kya baat! yaad kiya 🤭"],
        "evening": ["ohooo! shaam ho gayi aur ab yaad aaya? 😏", "arre kahan the hero? 😂"],
        "night": ["ohooo! raat ko miss kiya? 😏", "itni raat ko? interesting 🤭"],
    },
    "CARING": {
        "morning": ["good morning baby! 💕 neend achi hui?", "morning! 🥺 kaise ho aaj?", "subah ho gayi! dhoop mein mat jana 💕"],
        "afternoon": ["hii baby! 💕 lunch kiya?", "sun na, khana khaya? 🥺", "arey! kaise ho? sab theek? 💕"],
        "evening": ["hii! 💕 thak gaye honge aaj", "sun na, kaise raha din? 🥺", "shaam ho gayi, aaram karo 💕"],
        "night": ["baby! itni raat ko? 🥺 sab theek?", "so nahi paa rahe? main hoon na 💕", "raat ho gayi, neend nahi aa rahi? 🥺"],
    },
    "CURIOUS": {
        "morning": ["morning! kya plan hai aaj ka?", "hii! aaj kya karne wale ho?", "subah ho gayi! koi exciting plan?"],
        "afternoon": ["hii! kya chal raha hai? batao", "arey! kya kar rahe the abhi?", "bolo bolo, kya scene hai?"],
        "evening": ["hii! din kaisa raha? batao sab", "arey! kya interesting hua aaj?", "bolo, kya kiya aaj?"],
        "night": ["arey! abhi tak jaag rahe ho? kyun?", "kya ho raha hai itni raat ko?", "neend nahi aa rahi? kyun?"],
    },
}

# Memory-based greetings (when we know something about user)
MEMORY_GREETINGS = {
    "trip": ["arey! trip ka kya hua? plan final?", "waise wo trip plan, kab ja rahe ho?"],
    "badminton": ["arey! badminton khela aaj?", "kya scene hai game ka?"],
    "pubg": ["oye! PUBG khela aaj? 😏", "chicken dinner mila kya?"],
    "brother": ["अनुराग से baat hui?", "bhai kaisa hai?"],
    "work": ["office kaisa raha?", "kaam ka kya scene hai?"],
    "health": ["medicine li aaj?", "dhyan rakha apna?"],
}


class ResponsePlanner:
    """Plans response strategy before LLM generation."""
    
    # Quick responses that don't need LLM - NOW PERSONA-AWARE
    QUICK_RESPONSES = {
        IntentType.FAREWELL: {
            EmotionState.NEUTRAL: [
                "bye! 💕",
                "chal, milte hain!",
                "okay bye!",
            ],
            EmotionState.TIRED: [
                "soja jaldi! night 💕",
                "bye! rest karo",
            ],
        },
    }
    
    # Filler responses for very short user inputs
    ACKNOWLEDGMENTS = [
        "hmm...", "acha...", "ohh...", "okay...",
    ]
    
    def __init__(self, persona_engine: PersonaEngine | None = None):
        """
        Initialize response planner.
        
        Args:
            persona_engine: Optional PersonaEngine instance
        """
        self.persona = persona_engine or PersonaEngine()
        self._last_strategy: ResponseStrategy | None = None
        self._used_greetings: list[str] = []
    
    def _get_time_period(self) -> str:
        """Get current time period."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"
    
    def _get_persona_greeting(self, persona: str, time_period: str, memories: list = None) -> str:
        """Get a varied greeting based on persona, time, and memories."""
        
        # 30% chance to use memory-based greeting if we have relevant memories
        if memories and random.random() < 0.3:
            for mem in memories:
                mem_lower = str(mem).lower()
                for key, greetings in MEMORY_GREETINGS.items():
                    if key in mem_lower:
                        greeting = random.choice(greetings)
                        if greeting not in self._used_greetings[-5:]:
                            self._used_greetings.append(greeting)
                            return greeting
        
        # Get persona-specific greeting
        greetings = PERSONA_GREETINGS.get(persona, PERSONA_GREETINGS["CARING"])
        time_greetings = greetings.get(time_period, greetings["afternoon"])
        
        # Avoid recently used
        available = [g for g in time_greetings if g not in self._used_greetings[-3:]]
        if not available:
            available = time_greetings
        
        greeting = random.choice(available)
        self._used_greetings.append(greeting)
        self._used_greetings = self._used_greetings[-10:]
        
        return greeting
    
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
        current_persona: str = None,
        user_memories: list = None,
    ) -> str | None:
        """
        Get a quick cached response if available.
        NOW PERSONA-AWARE for greetings!
        
        Args:
            intent: Detected intent
            emotion: Detected emotion
            recent_responses: Recent responses to avoid
            current_persona: Current persona variant (CHILL/PLAYFUL/CARING/CURIOUS)
            user_memories: User memories for contextual greetings
            
        Returns:
            Quick response string or None
        """
        recent = recent_responses or []
        
        # GREETING: Use persona-specific greeting
        if intent == IntentType.GREETING:
            persona = current_persona or random.choice(["CHILL", "PLAYFUL", "CARING", "CURIOUS"])
            time_period = self._get_time_period()
            return self._get_persona_greeting(persona, time_period, user_memories)
        
        # For other intents, use standard quick responses
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
