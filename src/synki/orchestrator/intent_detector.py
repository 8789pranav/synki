"""
Intent Detector

Detects user intent from text to determine appropriate response type.
"""

import re

import structlog

from ..models import IntentType

logger = structlog.get_logger(__name__)


class IntentDetector:
    """Detects user intent from text."""
    
    # Intent patterns (Hindi + English)
    INTENT_PATTERNS: dict[IntentType, list[str]] = {
        IntentType.GREETING: [
            r"^(hi|hello|hey|hii+|helo|namaste|namaskar|kaise ho|kaisi ho)\b",
            r"^(good morning|good evening|good night|suprabhat)\b",
            r"^(what'?s up|wassup|kya haal|kya chal)\b",
        ],
        IntentType.FAREWELL: [
            r"\b(bye|goodbye|alvida|tata|see you|milte hai|good night|soja|chal)\b$",
            r"\b(gotta go|jaana hai|ab chalta|baad mein)\b",
            r"^(ok bye|accha bye|chalo bye)\b",
        ],
        IntentType.QUESTION: [
            r"^(kya|kaun|kahan|kab|kaise|kyun|kitna|konsa)\b",
            r"^(what|who|where|when|how|why|which|do you|can you|will you)\b",
            r"\?$",
        ],
        IntentType.REQUEST: [
            r"\b(please|plz|bata|batao|tell me|help|madad|suggest|recommend)\b",
            r"\b(can you|could you|will you|kya tum|would you)\b.*\?",
            r"\b(i want|i need|mujhe|chahiye)\b",
        ],
        IntentType.EMOTIONAL_SUPPORT: [
            r"\b(sad|dukhi|upset|cry|ro|miss|yaad|alone|akela)\b",
            r"\b(stressed|tension|anxious|worried|scared|dar)\b",
            r"\b(tired|exhausted|thak|drain|burnout)\b",
            r"\b(nobody|koi nahi|no one understands)\b",
        ],
        IntentType.TOPIC_CHANGE: [
            r"^(anyway|waise|btw|by the way|khair|accha sun)\b",
            r"^(let'?s talk about|baat karte|topic change)\b",
            r"\b(something else|kuch aur|different)\b",
        ],
        IntentType.STATEMENT: [
            r"^(main|mujhe|mere|mera|i |i'm|i am|my )\b",
            r"\b(today|aaj|kal|yesterday)\b",
            r"^(so |toh |actually |basically )",
        ],
    }
    
    def __init__(self):
        """Initialize intent detector with compiled patterns."""
        self._compiled_patterns: dict[IntentType, list[re.Pattern]] = {}
        for intent, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE) 
                for p in patterns
            ]
    
    def detect(self, text: str) -> tuple[IntentType, float]:
        """
        Detect intent from text.
        
        Args:
            text: User's text input
            
        Returns:
            Tuple of (detected intent, confidence score)
        """
        if not text or not text.strip():
            return IntentType.CASUAL_CHAT, 0.5
        
        text = text.strip()
        scores: dict[IntentType, float] = {}
        
        # Check each intent's patterns
        for intent, patterns in self._compiled_patterns.items():
            score = 0.0
            for pattern in patterns:
                if pattern.search(text):
                    score += 0.4
            scores[intent] = min(score, 1.0)
        
        # Find highest scoring intent
        if not scores or max(scores.values()) == 0:
            return IntentType.CASUAL_CHAT, 0.5
        
        best_intent = max(scores, key=lambda k: scores[k])
        confidence = scores[best_intent]
        
        # Minimum threshold
        if confidence < 0.3:
            return IntentType.CASUAL_CHAT, 0.5
        
        logger.debug(
            "intent_detected",
            text_preview=text[:50],
            intent=best_intent.value,
            confidence=confidence,
        )
        
        return best_intent, confidence
    
    def is_question(self, text: str) -> bool:
        """
        Quick check if text is a question.
        
        Args:
            text: User's text
            
        Returns:
            True if text appears to be a question
        """
        intent, _ = self.detect(text)
        return intent == IntentType.QUESTION
    
    def needs_emotional_response(self, text: str) -> bool:
        """
        Check if text needs an emotional/supportive response.
        
        Args:
            text: User's text
            
        Returns:
            True if emotional response is needed
        """
        intent, confidence = self.detect(text)
        return intent == IntentType.EMOTIONAL_SUPPORT and confidence > 0.3
    
    def is_conversation_ender(self, text: str) -> bool:
        """
        Check if text indicates end of conversation.
        
        Args:
            text: User's text
            
        Returns:
            True if user wants to end conversation
        """
        intent, confidence = self.detect(text)
        return intent == IntentType.FAREWELL and confidence > 0.4
    
    def get_response_type_hint(self, intent: IntentType) -> str:
        """
        Get hint for response type based on intent.
        
        Args:
            intent: Detected intent
            
        Returns:
            Response type hint
        """
        hints = {
            IntentType.GREETING: "respond with warm greeting, ask how they are",
            IntentType.FAREWELL: "say goodbye warmly, express care",
            IntentType.QUESTION: "answer the question naturally",
            IntentType.STATEMENT: "acknowledge and respond naturally",
            IntentType.REQUEST: "help fulfill the request",
            IntentType.EMOTIONAL_SUPPORT: "be empathetic, validate feelings",
            IntentType.CASUAL_CHAT: "engage naturally, show interest",
            IntentType.TOPIC_CHANGE: "smoothly transition to new topic",
        }
        return hints.get(intent, hints[IntentType.CASUAL_CHAT])
