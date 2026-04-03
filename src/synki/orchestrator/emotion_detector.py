"""
Emotion Detector

Detects user emotions from text using keyword analysis and patterns.
Can be extended with ML-based sentiment analysis.
"""

import re

import structlog

from ..models import EmotionState

logger = structlog.get_logger(__name__)


class EmotionDetector:
    """Detects emotions from user text."""
    
    # Emotion keyword patterns (Hindi + English)
    EMOTION_PATTERNS: dict[EmotionState, list[str]] = {
        EmotionState.HAPPY: [
            r"\b(khush|happy|great|amazing|awesome|mast|maza|accha laga|excited|yay)\b",
            r"(😊|😄|🎉|❤️|💕|🥰)",
            r"\b(finally|yayyy|woohoo)\b",
        ],
        EmotionState.SAD: [
            r"\b(sad|dukhi|upset|cry|ro|rona|miss|yaad|hurt|pain|dard)\b",
            r"(😢|😭|💔|😞|😔)",
            r"\b(alone|akela|lonely)\b",
        ],
        EmotionState.TIRED: [
            r"\b(tired|thak|thaki|exhausted|sleepy|neend|sone|drain|worn out)\b",
            r"(😴|🥱|😩)",
            r"\b(so tired|bahut thak|energy nahi)\b",
        ],
        EmotionState.STRESSED: [
            r"\b(stress|tension|pressure|overwhelm|bahut kaam|deadline|hectic)\b",
            r"(😰|😫|🤯)",
            r"\b(too much|bohot zyada|can't handle)\b",
        ],
        EmotionState.EXCITED: [
            r"\b(excited|pumped|can't wait|eager|thrilled|psyched)\b",
            r"(🎊|🤩|✨|🔥)",
            r"\b(omg|oh my god|wow)\b",
        ],
        EmotionState.BORED: [
            r"\b(bored|boring|bore|nothing to do|kuch nahi|sama nahi)\b",
            r"(😐|😑|🥱)",
            r"\b(so bored|bahut bore)\b",
        ],
        EmotionState.ANGRY: [
            r"\b(angry|gussa|irritated|annoyed|frustrated|pissed|mad)\b",
            r"(😠|😤|🤬|💢)",
            r"\b(hate|nafrat|can't stand)\b",
        ],
        EmotionState.ANXIOUS: [
            r"\b(anxious|worried|nervous|scared|dar|darr|fear|panic)\b",
            r"(😨|😱|😟|🥺)",
            r"\b(what if|kya hoga|tension)\b",
        ],
    }
    
    # Intensity modifiers
    INTENSITY_BOOSTERS = [
        r"\b(very|bahut|bohot|so|really|kaafi|ekdam|totally)\b",
    ]
    
    def __init__(self):
        """Initialize emotion detector with compiled patterns."""
        self._compiled_patterns: dict[EmotionState, list[re.Pattern]] = {}
        for emotion, patterns in self.EMOTION_PATTERNS.items():
            self._compiled_patterns[emotion] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        self._intensity_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.INTENSITY_BOOSTERS
        ]
    
    def detect(self, text: str) -> tuple[EmotionState, float]:
        """
        Detect emotion from text.
        
        Args:
            text: User's text input
            
        Returns:
            Tuple of (detected emotion, confidence score)
        """
        if not text or not text.strip():
            return EmotionState.NEUTRAL, 0.0
        
        text = text.strip()
        scores: dict[EmotionState, float] = {}
        
        # Check each emotion's patterns
        for emotion, patterns in self._compiled_patterns.items():
            score = 0.0
            for pattern in patterns:
                matches = pattern.findall(text)
                score += len(matches) * 0.3
            scores[emotion] = min(score, 1.0)  # Cap at 1.0
        
        # Find highest scoring emotion
        if not scores or max(scores.values()) == 0:
            return EmotionState.NEUTRAL, 0.5
        
        best_emotion = max(scores, key=lambda k: scores[k])
        confidence = scores[best_emotion]
        
        # Boost confidence if intensity modifiers present
        for pattern in self._intensity_patterns:
            if pattern.search(text):
                confidence = min(confidence + 0.2, 1.0)
                break
        
        # Require minimum confidence threshold
        if confidence < 0.2:
            return EmotionState.NEUTRAL, 0.5
        
        logger.debug(
            "emotion_detected",
            text_preview=text[:50],
            emotion=best_emotion.value,
            confidence=confidence,
        )
        
        return best_emotion, confidence
    
    def detect_from_history(
        self,
        messages: list[str],
        weights: list[float] | None = None,
    ) -> EmotionState:
        """
        Detect overall emotion from message history.
        
        Args:
            messages: List of recent messages (newest last)
            weights: Optional weights for each message (newest = highest)
            
        Returns:
            Overall emotion state
        """
        if not messages:
            return EmotionState.NEUTRAL
        
        # Default weights: more recent = more weight
        if weights is None:
            n = len(messages)
            weights = [(i + 1) / n for i in range(n)]
        
        # Detect emotions for each message
        emotion_scores: dict[EmotionState, float] = {}
        for msg, weight in zip(messages, weights):
            emotion, confidence = self.detect(msg)
            current = emotion_scores.get(emotion, 0.0)
            emotion_scores[emotion] = current + (confidence * weight)
        
        # Return highest weighted emotion
        if not emotion_scores:
            return EmotionState.NEUTRAL
        
        return max(emotion_scores, key=lambda k: emotion_scores[k])
    
    def get_emotion_response_hint(self, emotion: EmotionState) -> str:
        """
        Get response guidance based on detected emotion.
        
        Args:
            emotion: Detected emotion state
            
        Returns:
            Response hint string
        """
        hints = {
            EmotionState.HAPPY: "match their energy, be playful and celebratory",
            EmotionState.SAD: "be gentle, empathetic, offer comfort without fixing",
            EmotionState.TIRED: "be soothing, acknowledge their exhaustion, suggest rest",
            EmotionState.STRESSED: "be calming, validate their feelings, offer support",
            EmotionState.EXCITED: "share their excitement, be enthusiastic",
            EmotionState.BORED: "be engaging, suggest activities or interesting topics",
            EmotionState.ANGRY: "be understanding, don't dismiss, let them vent",
            EmotionState.ANXIOUS: "be reassuring, calm, help them feel safe",
            EmotionState.NEUTRAL: "be warm and engaging, show interest",
        }
        return hints.get(emotion, hints[EmotionState.NEUTRAL])
