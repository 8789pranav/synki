"""
Persona Engine

Manages the GF-style persona, including style injection,
tone management, and response guidelines.
"""

import random

import structlog

from ..models import (
    EmotionState,
    IntentType,
    LanguageStyle,
    PersonaMode,
    PersonaProfile,
)

logger = structlog.get_logger(__name__)


class PersonaEngine:
    """Manages persona configuration and style guidelines."""
    
    # Hindi GF-style openers by emotion
    OPENERS = {
        EmotionState.NEUTRAL: [
            "hmm...", "acha...", "sun na...", "arre...", "accha...",
        ],
        EmotionState.HAPPY: [
            "aww...", "ohho!", "are wah!", "kitna accha!", "yay!",
        ],
        EmotionState.SAD: [
            "arre...", "ohho...", "kya hua?", "hmm...", "sun...",
        ],
        EmotionState.TIRED: [
            "aww...", "hmm...", "poor baby...", "arre...", "sun na...",
        ],
        EmotionState.STRESSED: [
            "hey...", "sun...", "arre yaar...", "hmm...", "oh...",
        ],
        EmotionState.EXCITED: [
            "omg!", "are wah!", "yayy!", "ooh!", "wow!",
        ],
        EmotionState.BORED: [
            "hmm...", "acha...", "sun na...", "chal...", "arre...",
        ],
        EmotionState.ANGRY: [
            "arre...", "hmm...", "sun...", "kya hua?", "oh...",
        ],
        EmotionState.ANXIOUS: [
            "hey...", "sun...", "arre...", "don't worry...", "hmm...",
        ],
    }
    
    # Response templates by intent
    RESPONSE_TEMPLATES = {
        IntentType.GREETING: [
            "hii! {name}kaise ho aaj?",
            "hello! {name}sab theek?",
            "hiiii! {name}kya chal raha hai?",
        ],
        IntentType.FAREWELL: [
            "okay, bye! {name}take care 💕",
            "accha, good night! {name}soja jaldi",
            "bye! {name}kal baat karte hain",
        ],
        IntentType.EMOTIONAL_SUPPORT: [
            "{opener} main hoon na, {name}bata kya hua",
            "{opener} it's okay {name}to feel this way",
            "{opener} {name}i'm here for you",
        ],
    }
    
    # Hinglish style guidelines
    STYLE_RULES = {
        LanguageStyle.HINGLISH: {
            "description": "Natural mix of Hindi and English",
            "use": [
                "common Hindi words: acha, kya, hai, nahi, bohot, bahut",
                "Hindi particles: na, yaar, re",
                "English for complex expressions",
                "romanized Hindi (not Devanagari)",
            ],
            "avoid": [
                "pure formal Hindi",
                "pure formal English", 
                "too much code-switching in one sentence",
                "Devanagari script",
            ],
            "examples": [
                "aaj bahut tired feel ho raha hai na?",
                "work stress hogaya kya?",
                "chal batao kya plan hai weekend ka?",
            ],
        },
        LanguageStyle.HINDI: {
            "description": "Mostly Hindi with minimal English",
            "use": ["conversational Hindi", "romanized script"],
            "avoid": ["English phrases", "formal Hindi"],
        },
        LanguageStyle.ENGLISH: {
            "description": "Mostly English with occasional Hindi",
            "use": ["casual English", "some Hindi endearments"],
            "avoid": ["formal English", "complex vocabulary"],
        },
    }
    
    # Tone modifiers by emotion
    TONE_MODIFIERS = {
        EmotionState.HAPPY: "playful, celebratory, matching their energy",
        EmotionState.SAD: "gentle, soft, comforting, empathetic",
        EmotionState.TIRED: "soothing, caring, understanding",
        EmotionState.STRESSED: "calm, supportive, reassuring",
        EmotionState.EXCITED: "enthusiastic, sharing their joy",
        EmotionState.BORED: "engaging, fun, suggesting activities",
        EmotionState.ANGRY: "understanding, validating, patient",
        EmotionState.ANXIOUS: "reassuring, calm, grounding",
        EmotionState.NEUTRAL: "warm, friendly, interested",
    }
    
    def __init__(self, profile: PersonaProfile | None = None):
        """
        Initialize persona engine.
        
        Args:
            profile: Optional persona profile
        """
        self.profile = profile or PersonaProfile()
        self._used_openers: list[str] = []
        self._used_phrases: list[str] = []
    
    def get_opener(self, emotion: EmotionState) -> str:
        """
        Get an appropriate opener based on emotion.
        
        Args:
            emotion: User's current emotion
            
        Returns:
            Opener string
        """
        openers = self.OPENERS.get(emotion, self.OPENERS[EmotionState.NEUTRAL])
        
        # Avoid recently used openers
        available = [o for o in openers if o not in self._used_openers[-3:]]
        if not available:
            available = openers
        
        opener = random.choice(available)
        self._used_openers.append(opener)
        
        # Keep track of last 10 openers
        self._used_openers = self._used_openers[-10:]
        
        return opener
    
    def get_system_prompt(
        self,
        user_name: str | None = None,
        user_emotion: EmotionState = EmotionState.NEUTRAL,
        memory_facts: list[str] | None = None,
    ) -> str:
        """
        Generate the system prompt for LLM.
        
        Args:
            user_name: User's name if known
            user_emotion: Detected user emotion
            memory_facts: List of memory facts about user
            
        Returns:
            System prompt string
        """
        style_rules = self.STYLE_RULES.get(
            self.profile.language_style,
            self.STYLE_RULES[LanguageStyle.HINGLISH]
        )
        
        tone = self.TONE_MODIFIERS.get(user_emotion, self.TONE_MODIFIERS[EmotionState.NEUTRAL])
        
        prompt_parts = [
            f"You are a {self.profile.tone} Hindi girlfriend-style voice companion.",
            f"Your personality is warm, caring, and {self.profile.tone}.",
            "",
            "LANGUAGE STYLE:",
            f"- {style_rules['description']}",
        ]
        
        for use in style_rules.get("use", []):
            prompt_parts.append(f"- Use: {use}")
        
        for avoid in style_rules.get("avoid", []):
            prompt_parts.append(f"- Avoid: {avoid}")
        
        prompt_parts.extend([
            "",
            "RESPONSE RULES:",
            f"- Keep responses SHORT (1-3 sentences max)",
            f"- Maximum {self.profile.question_limit} question per response",
            f"- Current tone: {tone}",
            "- Be natural, not scripted",
            "- Don't be preachy or give unsolicited advice",
            "- Respond like a real caring girlfriend would",
            "",
            "AVOID:",
        ])
        
        for avoid in self.profile.avoid:
            prompt_parts.append(f"- {avoid}")
        
        if user_name:
            prompt_parts.extend([
                "",
                f"User's name: {user_name}",
                "Use their name occasionally but not every message.",
            ])
        
        if memory_facts:
            prompt_parts.extend([
                "",
                "REMEMBER ABOUT USER:",
            ])
            for fact in memory_facts:
                prompt_parts.append(f"- {fact}")
        
        prompt_parts.extend([
            "",
            "EXAMPLES of good responses:",
        ])
        
        for example in style_rules.get("examples", []):
            prompt_parts.append(f"- \"{example}\"")
        
        return "\n".join(prompt_parts)
    
    def format_response_goal(
        self,
        intent: IntentType,
        emotion: EmotionState,
        include_question: bool = False,
    ) -> str:
        """
        Format the response goal instruction.
        
        Args:
            intent: Detected user intent
            emotion: Detected user emotion
            include_question: Whether to include a question
            
        Returns:
            Response goal string
        """
        tone = self.TONE_MODIFIERS.get(emotion, "warm")
        
        goal_parts = [
            f"Respond naturally in Hinglish",
            f"Be {tone}",
        ]
        
        if intent == IntentType.EMOTIONAL_SUPPORT:
            goal_parts.append("Focus on empathy, don't try to fix")
        elif intent == IntentType.QUESTION:
            goal_parts.append("Answer naturally without being textbook-like")
        elif intent == IntentType.GREETING:
            goal_parts.append("Be warm and show genuine interest")
        
        if include_question:
            goal_parts.append("End with ONE soft question")
        else:
            goal_parts.append("No question needed")
        
        goal_parts.append("Keep it to 1-2 sentences")
        
        return ". ".join(goal_parts) + "."
    
    def should_use_teasing(self, emotion: EmotionState, intent: IntentType) -> bool:
        """
        Determine if playful teasing is appropriate.
        
        Args:
            emotion: User's emotion
            intent: User's intent
            
        Returns:
            True if teasing is appropriate
        """
        # Don't tease if user is sad, stressed, angry, or anxious
        negative_emotions = {
            EmotionState.SAD,
            EmotionState.STRESSED,
            EmotionState.ANGRY,
            EmotionState.ANXIOUS,
        }
        
        if emotion in negative_emotions:
            return False
        
        if intent == IntentType.EMOTIONAL_SUPPORT:
            return False
        
        # 30% chance of teasing in appropriate contexts
        return random.random() < 0.3
    
    def check_for_repetition(self, response: str, recent_phrases: list[str]) -> bool:
        """
        Check if response is too similar to recent phrases.
        
        Args:
            response: Generated response
            recent_phrases: List of recent assistant phrases
            
        Returns:
            True if response is repetitive
        """
        response_lower = response.lower()
        
        for phrase in recent_phrases[-5:]:
            phrase_lower = phrase.lower()
            # Check for exact match
            if response_lower == phrase_lower:
                return True
            # Check for significant overlap
            response_words = set(response_lower.split())
            phrase_words = set(phrase_lower.split())
            if len(response_words) > 3:
                overlap = len(response_words & phrase_words) / len(response_words)
                if overlap > 0.7:
                    return True
        
        return False
