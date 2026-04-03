"""
Synki Models Module

Data models and schemas used throughout the application.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class PersonaMode(str, Enum):
    """Available persona modes."""
    GIRLFRIEND = "girlfriend"
    FRIEND = "friend"
    MENTOR = "mentor"


class LanguageStyle(str, Enum):
    """Language style options."""
    HINGLISH = "hinglish"
    HINDI = "hindi"
    ENGLISH = "english"


class EmotionState(str, Enum):
    """Detected user emotion states."""
    HAPPY = "happy"
    SAD = "sad"
    TIRED = "tired"
    STRESSED = "stressed"
    EXCITED = "excited"
    BORED = "bored"
    NEUTRAL = "neutral"
    ANGRY = "angry"
    ANXIOUS = "anxious"


class IntentType(str, Enum):
    """User intent categories."""
    GREETING = "greeting"
    FAREWELL = "farewell"
    QUESTION = "question"
    STATEMENT = "statement"
    REQUEST = "request"
    EMOTIONAL_SUPPORT = "emotional_support"
    CASUAL_CHAT = "casual_chat"
    TOPIC_CHANGE = "topic_change"


class ResponseStrategy(str, Enum):
    """Response generation strategies."""
    CACHED_OPENER = "cached_opener"
    SHORT_RESPONSE = "short_response"
    FULL_RESPONSE = "full_response"
    EMOTIONAL_RESPONSE = "emotional_response"
    PLAYFUL_TEASE = "playful_tease"


# =============================================================================
# Transcript Models
# =============================================================================

class TranscriptEvent(BaseModel):
    """Transcript event from STT service."""
    
    session_id: str
    type: Literal["partial_transcript", "final_transcript"] = "partial_transcript"
    text: str
    is_final: bool = False
    speech_final: bool = False
    confidence: float = 0.0
    timestamp_ms: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    words: list[dict[str, Any]] = Field(default_factory=list)


# =============================================================================
# Persona Models
# =============================================================================

class PersonaProfile(BaseModel):
    """Persona configuration profile."""
    
    mode: PersonaMode = PersonaMode.GIRLFRIEND
    language_style: LanguageStyle = LanguageStyle.HINGLISH
    tone: str = "soft, caring, slightly playful"
    question_limit: int = 1  # Max questions per response
    emoji_level: Literal["none", "low", "medium", "high"] = "low"
    avoid: list[str] = Field(default_factory=lambda: [
        "formal Hindi",
        "robotic phrasing", 
        "too many questions",
        "repetitive phrases",
        "generic responses"
    ])
    preferred_openers: list[str] = Field(default_factory=lambda: [
        "hmm...",
        "acha...",
        "ohho...",
        "are...",
        "sun...",
    ])


# =============================================================================
# Context Models
# =============================================================================

class ContextPacket(BaseModel):
    """Current turn context information."""
    
    recent_user_messages: list[str] = Field(default_factory=list, max_length=5)
    recent_assistant_messages: list[str] = Field(default_factory=list, max_length=5)
    current_topic: str = ""
    last_mood: EmotionState = EmotionState.NEUTRAL
    last_intent: IntentType = IntentType.CASUAL_CHAT
    turn_count: int = 0
    session_duration_ms: int = 0


class LongTermMemory(BaseModel):
    """Stable user facts for personalization."""
    
    user_id: str
    name: str | None = None
    nickname: str | None = None
    favorite_genres: list[str] = Field(default_factory=list)
    sleep_pattern: str | None = None
    work_schedule: str | None = None
    common_states: list[str] = Field(default_factory=list)
    preferred_language: LanguageStyle = LanguageStyle.HINGLISH
    interests: list[str] = Field(default_factory=list)
    pet_names_used: list[str] = Field(default_factory=list)
    important_dates: dict[str, str] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=datetime.now)


# =============================================================================
# LLM Models
# =============================================================================

class LLMInputPacket(BaseModel):
    """Input packet for LLM generation."""
    
    persona_mode: PersonaMode
    style: str
    user_text: str
    recent_context: list[str] = Field(default_factory=list)
    memory_facts: list[str] = Field(default_factory=list)
    response_goal: str = ""
    emotion: EmotionState = EmotionState.NEUTRAL
    strategy: ResponseStrategy = ResponseStrategy.FULL_RESPONSE


class ResponsePlan(BaseModel):
    """Response planning output."""
    
    strategy: ResponseStrategy
    use_opener: bool = True
    opener: str = ""
    warmth_level: Literal["low", "medium", "high"] = "medium"
    include_question: bool = False
    avoid_phrases: list[str] = Field(default_factory=list)
    max_sentences: int = 3


# =============================================================================
# TTS Models
# =============================================================================

class TTSRequest(BaseModel):
    """TTS request unit."""
    
    context_id: str
    text_chunk: str
    voice_id: str
    emotion: str = "soft_caring"
    continue_context: bool = True


# =============================================================================
# Session Models
# =============================================================================

class SessionState(BaseModel):
    """Current session state."""
    
    session_id: str
    user_id: str
    room_name: str
    started_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    turn_count: int = 0
    persona: PersonaProfile = Field(default_factory=PersonaProfile)
    context: ContextPacket = Field(default_factory=ContextPacket)
    is_speaking: bool = False
    is_listening: bool = True
    recent_phrases: list[str] = Field(default_factory=list)
