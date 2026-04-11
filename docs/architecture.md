# Synki Architecture Documentation

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Data Flow](#data-flow)
4. [Component Details](#component-details)
5. [Sequence Diagrams](#sequence-diagrams)
6. [Service Integrations](#service-integrations)
7. [Configuration Reference](#configuration-reference)

---

## Overview

Synki is a **real-time voice AI companion** designed for natural, low-latency conversations in Hinglish (Hindi + English). The system processes speech input, understands context and emotion, generates personality-consistent responses, and synthesizes natural-sounding speech—all in under 2 seconds.

### Design Principles

| Principle | Description |
|-----------|-------------|
| **Low Latency First** | Every component optimized for minimal delay |
| **Streaming Everything** | No waiting for complete results - stream STT, LLM, and TTS |
| **Personality Consistency** | Maintain character through orchestration, not just prompts |
| **Anti-Repetition** | Track recent phrases to avoid robotic repetition |
| **Context Awareness** | Remember both short-term conversation and long-term facts |
| **Graceful Degradation** | Fallback paths when optional features unavailable |

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 CLIENT LAYER                                         │
│  ┌───────────────────────────────────────────────────────────────────────────────┐  │
│  │  Web Browser / Mobile App                                                      │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │  │
│  │  │  Microphone │  │  Speaker    │  │  LiveKit    │  │  UI State   │          │  │
│  │  │  Capture    │  │  Playback   │  │  Client SDK │  │  Manager    │          │  │
│  │  └──────┬──────┘  └──────▲──────┘  └──────┬──────┘  └─────────────┘          │  │
│  │         │                │                │                                    │  │
│  │         └────────────────┼────────────────┘                                    │  │
│  └──────────────────────────┼────────────────────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────────────────────────┘
                              │ WebRTC (Opus Audio)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               TRANSPORT LAYER                                        │
│  ┌───────────────────────────────────────────────────────────────────────────────┐  │
│  │  LiveKit Cloud (wss://zupki-hv3uw8fv.livekit.cloud)                           │  │
│  │                                                                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  LiveKit Room                                                            │  │  │
│  │  │  ┌───────────────────┐              ┌───────────────────┐               │  │  │
│  │  │  │  User Participant │              │  Agent Participant │               │  │  │
│  │  │  │  • Audio Track    │◄────────────►│  • Audio Track     │               │  │  │
│  │  │  │    (published)    │   Subscribe  │    (published)     │               │  │  │
│  │  │  └───────────────────┘              └───────────────────┘               │  │  │
│  │  └─────────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                                │  │
│  │  Features:                                                                     │  │
│  │  • ICE/TURN/STUN for NAT traversal                                            │  │
│  │  • DTLS encryption                                                             │  │
│  │  • Adaptive bitrate                                                            │  │
│  │  • Room-based architecture                                                     │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────────────────────────┘
                              │ Agent SDK
                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                AGENT LAYER                                           │
│  ┌───────────────────────────────────────────────────────────────────────────────┐  │
│  │  Synki Agent Server (Python)                                                   │  │
│  │                                                                                │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  agent.py - Entry Point                                                  │  │  │
│  │  │  • AgentServer initialization                                            │  │  │
│  │  │  • Session handling (@server.rtc_session)                                │  │  │
│  │  │  • SynkiAssistant class (personality & instructions)                     │  │  │
│  │  └─────────────────────────────────────────────────────────────────────────┘  │  │
│  │                                        │                                       │  │
│  │                                        ▼                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  AgentSession - Voice Pipeline                                           │  │  │
│  │  │                                                                          │  │  │
│  │  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐             │  │  │
│  │  │  │   VAD    │──►│   STT    │──►│   LLM    │──►│   TTS    │             │  │  │
│  │  │  │ (Silero) │   │(Deepgram)│   │ (OpenAI) │   │(Cartesia)│             │  │  │
│  │  │  └──────────┘   └──────────┘   └──────────┘   └──────────┘             │  │  │
│  │  │                                                                          │  │  │
│  │  │  Configuration:                                                          │  │  │
│  │  │  • stt: "deepgram/nova-3:multi"                                         │  │  │
│  │  │  • llm: "openai/gpt-4.1-mini"                                           │  │  │
│  │  │  • tts: "cartesia/sonic-3:00a77add-48d5-4ef6-8157-71e5437b282d"        │  │  │
│  │  └─────────────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Interaction Map

```
                                    ┌─────────────────────┐
                                    │    User Speech      │
                                    └──────────┬──────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              VOICE ACTIVITY DETECTION                                 │
│  ┌────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Silero VAD                                                                     │ │
│  │  • Detects speech vs silence                                                    │ │
│  │  • Triggers STT only when speech detected                                       │ │
│  │  • Reduces API costs and latency                                                │ │
│  └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬───────────────────────────────────────────────────┘
                                   │ Speech Detected
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              SPEECH-TO-TEXT (DEEPGRAM)                               │
│  ┌────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Model: nova-3:multi (Multi-language)                                          │ │
│  │                                                                                 │ │
│  │  Features:                                                                      │ │
│  │  • Streaming transcription (interim + final results)                           │ │
│  │  • Hindi + English code-switching support                                       │ │
│  │  • Automatic punctuation                                                        │ │
│  │  • Endpointing (300ms silence = end of utterance)                              │ │
│  │                                                                                 │ │
│  │  Output: TranscriptEvent { text, is_final, confidence }                        │ │
│  └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬───────────────────────────────────────────────────┘
                                   │ Transcript Text
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                    ORCHESTRATOR                                       │
│                                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │   Session   │  │   Context   │  │   Emotion   │  │   Intent    │                 │
│  │   Manager   │  │   Manager   │  │   Detector  │  │   Detector  │                 │
│  │             │  │             │  │             │  │             │                 │
│  │ • Create    │  │ • Track     │  │ • Regex     │  │ • Classify  │                 │
│  │   session   │  │   history   │  │   patterns  │  │   input     │                 │
│  │ • Load/Save │  │ • Topic     │  │ • Hindi +   │  │ • Route     │                 │
│  │   state     │  │   detection │  │   English   │  │   response  │                 │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
│         │                │                │                │                         │
│         └────────────────┼────────────────┼────────────────┘                         │
│                          │                │                                          │
│                          ▼                ▼                                          │
│  ┌─────────────┐  ┌─────────────────────────────────────────┐  ┌─────────────┐      │
│  │   Memory    │  │            Response Planner             │  │   Persona   │      │
│  │   Service   │  │                                         │  │   Engine    │      │
│  │             │  │  • Select strategy based on:            │  │             │      │
│  │ • Store     │  │    - Intent type                        │  │ • GF        │      │
│  │   facts     │  │    - Emotion state                      │  │   personality│     │
│  │ • Retrieve  │  │    - Context                            │  │ • System    │      │
│  │   memories  │  │  • Avoid repetition                     │  │   prompts   │      │
│  │ • Redis     │  │  • Fast path for greetings              │  │ • Openers   │      │
│  └─────────────┘  └─────────────────────────────────────────┘  └─────────────┘      │
│                                        │                                             │
│                                        ▼                                             │
│                          ┌─────────────────────────────┐                            │
│                          │       LLMInputPacket        │                            │
│                          │  • system_prompt            │                            │
│                          │  • user_message             │                            │
│                          │  • context_messages         │                            │
│                          │  • response_strategy        │                            │
│                          └─────────────────────────────┘                            │
└──────────────────────────────────┬───────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            LANGUAGE MODEL (OPENAI)                                    │
│  ┌────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Model: gpt-4.1-mini                                                           │ │
│  │                                                                                 │ │
│  │  Input:                                                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  System: "You are Synki, a loving girlfriend..."                        │  │ │
│  │  │  Context: [recent messages]                                              │  │ │
│  │  │  User: "aaj bahut thak gaya"                                            │  │ │
│  │  └─────────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                                 │ │
│  │  Output (Streaming):                                                            │ │
│  │  "aww" → " baby" → "," → " इतना" → " थक" → " गए?" → ...                       │ │
│  │                                                                                 │ │
│  │  Configuration:                                                                 │ │
│  │  • temperature: 0.8 (creative but consistent)                                  │ │
│  │  • max_tokens: 150 (short responses)                                           │ │
│  │  • stream: true (for low latency)                                              │ │
│  └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬───────────────────────────────────────────────────┘
                                   │ Streaming Text
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           TEXT-TO-SPEECH (CARTESIA)                                   │
│  ┌────────────────────────────────────────────────────────────────────────────────┐ │
│  │  Model: sonic-3                                                                 │ │
│  │  Voice: Yogini (00a77add-48d5-4ef6-8157-71e5437b282d) - Indian Female          │ │
│  │                                                                                 │ │
│  │  Features:                                                                      │ │
│  │  • WebSocket streaming input                                                    │ │
│  │  • Context-based synthesis (maintains prosody across chunks)                    │ │
│  │  • Hindi (Devanagari) + English pronunciation                                   │ │
│  │  • Emotional intonation                                                         │ │
│  │                                                                                 │ │
│  │  Processing:                                                                    │ │
│  │  Text chunks ──► Sentence buffering ──► TTS synthesis ──► Audio chunks         │ │
│  │                                                                                 │ │
│  │  Output: PCM Audio (24kHz, 16-bit)                                             │ │
│  └────────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬───────────────────────────────────────────────────┘
                                   │ Audio Stream
                                   ▼
                          ┌─────────────────────┐
                          │   User Playback     │
                          │   (via LiveKit)     │
                          └─────────────────────┘
```

---

## Data Flow

### Complete Request-Response Flow

```
Timeline ─────────────────────────────────────────────────────────────────────►

User Speaking          STT Processing        LLM Generation       TTS & Playback
│                      │                     │                    │
├──[Speech Start]──────┤                     │                    │
│  "aaj bahut..."      │                     │                    │
│                      ├──[Interim: "aaj"]───┤                    │
│                      │                     │                    │
│  "...thak gaya"      │                     │                    │
│                      ├──[Interim: "aaj     │                    │
│                      │   bahut thak"]──────┤                    │
│                      │                     │                    │
├──[Speech End]────────┤                     │                    │
│  (300ms silence)     │                     │                    │
│                      ├──[Final: "aaj       │                    │
│                      │   bahut thak gaya"]─┤                    │
│                      │                     ├──[Start LLM]───────┤
│                      │                     │                    │
│                      │                     ├──[Token: "aww"]────┤
│                      │                     │                    ├──[Buffer]
│                      │                     ├──[Token: "baby,"]──┤
│                      │                     │                    ├──[Buffer]
│                      │                     ├──[Token: "इतना"]───┤
│                      │                     │                    ├──[Buffer]
│                      │                     ├──[Token: "थक"]─────┤
│                      │                     │                    ├──[Buffer]
│                      │                     ├──[Token: "गए?"]────┤
│                      │                     │                    ├──[Sentence
│                      │                     │                    │   Complete!]
│                      │                     │                    │
│                      │                     │                    ├──[TTS Start]
│                      │                     │                    │
│                      │                     │                    ├──[Audio Out]
│                      │                     │                    │   User hears
│                      │                     │                    │   response
│                      │                     │                    │
◄─────────────────────────── ~1.7 seconds ───────────────────────────────────────►
```

### Data Models Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATA TRANSFORMATION                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │           Raw Audio                   │
                    │  (WebRTC Opus packets)                │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │         TranscriptEvent              │
                    │  {                                   │
                    │    text: "aaj bahut thak gaya",     │
                    │    is_final: true,                   │
                    │    confidence: 0.95,                 │
                    │    timestamp: 1234567890             │
                    │  }                                   │
                    └──────────────────┬───────────────────┘
                                       │
                    ┌──────────────────┼───────────────────┐
                    │                  │                   │
                    ▼                  ▼                   ▼
        ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
        │  EmotionState     │ │  IntentType       │ │  ContextPacket    │
        │                   │ │                   │ │                   │
        │  TIRED            │ │  STATEMENT        │ │  {                │
        │  (detected from   │ │  (classified      │ │    recent_msgs:   │
        │   "thak gaya")    │ │   from input)     │ │      [...],       │
        │                   │ │                   │ │    topic: "day",  │
        └─────────┬─────────┘ └─────────┬─────────┘ │    user_facts:    │
                  │                     │           │      {...}        │
                  │                     │           │  }                │
                  │                     │           └─────────┬─────────┘
                  │                     │                     │
                  └─────────────────────┼─────────────────────┘
                                        │
                                        ▼
                    ┌──────────────────────────────────────┐
                    │           ResponsePlan               │
                    │  {                                   │
                    │    strategy: EMOTIONAL_RESPONSE,     │
                    │    opener: null,                     │
                    │    tone_modifiers: ["caring"],       │
                    │    max_length: 50                    │
                    │  }                                   │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │          LLMInputPacket              │
                    │  {                                   │
                    │    system_prompt: "You are Synki...",│
                    │    user_message: "aaj bahut thak...",│
                    │    context_messages: [               │
                    │      {role: "user", content: "hi"},  │
                    │      {role: "assistant", content:    │
                    │        "hello baby!"}                │
                    │    ],                                │
                    │    response_strategy: EMOTIONAL,     │
                    │    emotion_hint: TIRED               │
                    │  }                                   │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │        Streaming LLM Output          │
                    │  AsyncIterator[str]                  │
                    │                                      │
                    │  "aww" → " baby" → "," → " इतना"    │
                    │  → " थक" → " गए?" → ...             │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │        Sentence Buffer               │
                    │                                      │
                    │  Accumulate until: . ? ! or 15 words │
                    │                                      │
                    │  "aww baby, इतना थक गए?"            │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │          TTSRequest                  │
                    │  {                                   │
                    │    text: "aww baby, इतना थक गए?",   │
                    │    voice_id: "00a77add-...",         │
                    │    context_id: "ctx_abc123"          │
                    │  }                                   │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────────────┐
                    │         Audio Stream                 │
                    │  AsyncIterator[bytes]                │
                    │                                      │
                    │  PCM chunks → Opus encoding →        │
                    │  WebRTC packets → User speaker       │
                    └──────────────────────────────────────┘
```

---

## Component Details

### 1. Session Manager

**Purpose**: Manages conversation sessions and their lifecycle.

**File**: `src/synki/orchestrator/session_manager.py`

```python
class SessionManager:
    """
    Responsibilities:
    - Create new sessions with unique IDs
    - Load existing session state
    - Save session state (optionally to Redis)
    - Handle session timeouts and cleanup
    """

    async def create_session(
        self,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> SessionState:
        """Create a new conversation session."""

    async def get_session(self, session_id: str) -> SessionState | None:
        """Retrieve existing session."""

    async def update_session(self, session: SessionState) -> None:
        """Persist session state."""
```

**Data Model**:

```python
class SessionState:
    id: str                          # Unique session identifier
    user_id: str | None              # Optional user identifier
    created_at: datetime             # Session start time
    last_activity: datetime          # Last interaction time
    turn_count: int                  # Number of conversation turns
    persona: PersonaProfile          # Active personality
    context: ContextPacket           # Current context
    metadata: dict                   # Custom metadata
```

---

### 2. Context Manager

**Purpose**: Tracks conversation history and detects topics.

**File**: `src/synki/orchestrator/context_manager.py`

```python
class ContextManager:
    """
    Responsibilities:
    - Maintain sliding window of recent messages
    - Detect conversation topic
    - Build compact context for LLM
    - Track mentioned entities
    """

    def add_message(
        self,
        role: str,  # "user" or "assistant"
        content: str,
    ) -> None:
        """Add message to context window."""

    def get_context(self) -> ContextPacket:
        """Get current context for LLM."""

    def detect_topic(self, text: str) -> str | None:
        """Detect topic from recent messages."""
```

**Context Window Strategy**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXT WINDOW (Last 5)                       │
├─────────────────────────────────────────────────────────────────┤
│  Turn 1: User: "hi baby"                                        │
│          Assistant: "hey जान! कैसे हो?"                         │
│  Turn 2: User: "thoda tired hun"                                │
│          Assistant: "aww, क्या हुआ? rest करो ना"                │
│  Turn 3: User: "office mein kaam zyada tha"  ◄── Current        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Topic Detected: "work"
```

---

### 3. Emotion Detector

**Purpose**: Detects user's emotional state from text.

**File**: `src/synki/orchestrator/emotion_detector.py`

```python
class EmotionDetector:
    """
    Pattern-based emotion detection for Hindi and English.

    Emotions Detected:
    - NEUTRAL: Default state
    - HAPPY: Joy, excitement, celebration
    - SAD: Sorrow, disappointment
    - TIRED: Exhaustion, sleepiness
    - FRUSTRATED: Anger, annoyance
    - EXCITED: Enthusiasm, anticipation
    - LOVING: Affection, romance
    """

    def detect(self, text: str) -> EmotionState:
        """Detect primary emotion from text."""

    def detect_all(self, text: str) -> list[tuple[EmotionState, float]]:
        """Detect all emotions with confidence scores."""
```

**Detection Patterns**:

```python
EMOTION_PATTERNS = {
    EmotionState.TIRED: [
        r"\b(tired|thak|thaki|exhausted|sleepy|neend)\b",
        r"\b(थक|थकी|नींद|सो जाना)\b",
        r"(😴|🥱|😩)",
    ],
    EmotionState.HAPPY: [
        r"\b(happy|khush|khushi|amazing|great|awesome)\b",
        r"\b(खुश|खुशी|मज़ा)\b",
        r"(😊|😄|🎉|❤️)",
    ],
    EmotionState.SAD: [
        r"\b(sad|dukhi|upset|crying|miss)\b",
        r"\b(दुखी|रोना|याद आ रही)\b",
        r"(😢|😭|💔)",
    ],
    # ... more patterns
}
```

---

### 4. Intent Detector

**Purpose**: Classifies user input to route response strategy.

**File**: `src/synki/orchestrator/intent_detector.py`

```python
class IntentDetector:
    """
    Classifies user input into intent categories.

    Intent Types:
    - GREETING: "hi", "hello", "hey"
    - FAREWELL: "bye", "goodnight", "talk later"
    - QUESTION: Direct questions ("kya", "how", "why")
    - STATEMENT: Declarative statements
    - EMOTIONAL_SUPPORT: Venting, seeking comfort
    - CASUAL_CHAT: General conversation
    """

    def classify(self, text: str) -> IntentType:
        """Classify input into intent category."""

    def get_sub_intent(self, text: str, intent: IntentType) -> str | None:
        """Get more specific sub-intent if available."""
```

**Classification Flow**:

```
Input: "aaj promotion mil gayi!"
           │
           ▼
┌─────────────────────────────────────┐
│  1. Check for greetings/farewells   │ ──► No match
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  2. Check for question markers      │ ──► No match
│     (kya, how, why, ?)              │
└─────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│  3. Check for emotional keywords    │ ──► Match: "promotion"
│     (positive achievement)          │     → EMOTIONAL_SUPPORT
└─────────────────────────────────────┘
           │
           ▼
   Intent: EMOTIONAL_SUPPORT
   Sub-intent: "celebration"
```

---

### 5. Persona Engine

**Purpose**: Manages the girlfriend personality and generates prompts.

**File**: `src/synki/orchestrator/persona_engine.py`

```python
class PersonaEngine:
    """
    Manages the GF personality configuration.

    Responsibilities:
    - Generate system prompts
    - Select appropriate openers
    - Apply style rules
    - Manage anti-repetition
    """

    def get_system_prompt(
        self,
        emotion: EmotionState,
        context: ContextPacket,
    ) -> str:
        """Generate system prompt for LLM."""

    def get_opener(
        self,
        intent: IntentType,
        emotion: EmotionState,
    ) -> str | None:
        """Get cached opener for fast response."""

    def should_avoid(self, phrase: str) -> bool:
        """Check if phrase was recently used."""
```

**Persona Configuration**:

```python
class PersonaProfile:
    mode: PersonaMode = PersonaMode.GIRLFRIEND
    language_style: LanguageStyle = LanguageStyle.HINGLISH
    tone: str = "soft, caring, playful"
    question_limit: int = 1              # Max questions per response
    pet_names: list[str] = ["baby", "जान", "sweetheart"]
    openers: dict[str, list[str]] = {
        "greeting": ["hey baby!", "aww, आ गए!"],
        "emotional_support": ["aww, क्या हुआ जान?"],
        # ...
    }
```

---

### 6. Response Planner

**Purpose**: Decides response strategy based on context.

**File**: `src/synki/orchestrator/response_planner.py`

```python
class ResponsePlanner:
    """
    Determines how to respond based on:
    - Intent type
    - Emotion state
    - Context
    - Recent response history

    Strategies:
    - CACHED_OPENER: Pre-defined fast response (~100ms)
    - SHORT_RESPONSE: 1-2 sentences
    - FULL_RESPONSE: Complete LLM response
    - EMOTIONAL_RESPONSE: Empathetic response
    - PLAYFUL_TEASE: Flirty/playful response
    """

    def plan(
        self,
        intent: IntentType,
        emotion: EmotionState,
        context: ContextPacket,
    ) -> ResponsePlan:
        """Create response plan."""
```

**Strategy Selection Matrix**:

```
                    │  NEUTRAL  │  HAPPY   │   SAD    │  TIRED   │
────────────────────┼───────────┼──────────┼──────────┼──────────┤
GREETING            │  CACHED   │  CACHED  │  SHORT   │  SHORT   │
FAREWELL            │  CACHED   │  CACHED  │  EMOTIONAL│ EMOTIONAL│
QUESTION            │  FULL     │  FULL    │  FULL    │  FULL    │
STATEMENT           │  SHORT    │  PLAYFUL │  EMOTIONAL│ EMOTIONAL│
EMOTIONAL_SUPPORT   │  EMOTIONAL│  PLAYFUL │  EMOTIONAL│ EMOTIONAL│
CASUAL_CHAT         │  SHORT    │  PLAYFUL │  SHORT   │  SHORT   │
```

---

### 7. Memory Service

**Purpose**: Stores and retrieves long-term user facts.

**File**: `src/synki/orchestrator/memory_service.py`

```python
class MemoryService:
    """
    Long-term memory for user facts.

    Stored Facts:
    - User's name
    - Preferences (food, music, etc.)
    - Common emotional states
    - Important dates
    - Conversation patterns

    Backend: Redis (optional, in-memory fallback)
    """

    async def store_fact(
        self,
        user_id: str,
        fact_type: str,
        value: str,
    ) -> None:
        """Store a user fact."""

    async def get_facts(self, user_id: str) -> dict:
        """Retrieve all facts for user."""

    async def learn_from_conversation(
        self,
        user_id: str,
        transcript: str,
    ) -> None:
        """Extract and store facts from conversation."""
```

**Fact Extraction Patterns**:

```python
FACT_EXTRACTORS = {
    "name": [
        r"(?:my name is|mera naam|i'm|i am)\s+(\w+)",
        r"(?:call me)\s+(\w+)",
    ],
    "work": [
        r"(?:i work at|mein kaam karta|job at)\s+(.+)",
    ],
    "preference": [
        r"(?:i love|mujhe pasand|favorite)\s+(.+)",
    ],
}
```

---

## Sequence Diagrams

### 1. New Session Flow

```
┌──────┐          ┌─────────┐          ┌─────────┐          ┌─────────┐
│Client│          │ LiveKit │          │  Agent  │          │Orchestr.│
└──┬───┘          └────┬────┘          └────┬────┘          └────┬────┘
   │                   │                    │                    │
   │  Connect to Room  │                    │                    │
   │──────────────────►│                    │                    │
   │                   │                    │                    │
   │  Room Joined      │                    │                    │
   │◄──────────────────│                    │                    │
   │                   │                    │                    │
   │                   │  New Participant   │                    │
   │                   │   (User Joined)    │                    │
   │                   │───────────────────►│                    │
   │                   │                    │                    │
   │                   │                    │  Create Session    │
   │                   │                    │───────────────────►│
   │                   │                    │                    │
   │                   │                    │  SessionState      │
   │                   │                    │◄───────────────────│
   │                   │                    │                    │
   │                   │  Agent Joined      │                    │
   │                   │◄───────────────────│                    │
   │                   │                    │                    │
   │  Agent Track      │                    │                    │
   │   Subscribed      │                    │                    │
   │◄──────────────────│                    │                    │
   │                   │                    │                    │
```

### 2. Voice Interaction Flow

```
┌──────┐     ┌─────────┐     ┌─────┐     ┌──────┐     ┌─────┐     ┌─────┐
│Client│     │ LiveKit │     │ VAD │     │ STT  │     │ LLM │     │ TTS │
└──┬───┘     └────┬────┘     └──┬──┘     └──┬───┘     └──┬──┘     └──┬──┘
   │              │             │           │            │           │
   │ Audio Stream │             │           │            │           │
   │─────────────►│             │           │            │           │
   │              │ Audio       │           │            │           │
   │              │────────────►│           │            │           │
   │              │             │           │            │           │
   │              │             │ Speech    │            │           │
   │              │             │ Detected  │            │           │
   │              │             │──────────►│            │           │
   │              │             │           │            │           │
   │              │             │           │ Interim    │           │
   │              │             │           │ Transcript │           │
   │              │             │           │───────────►│           │
   │              │             │           │ (early     │           │
   │              │             │           │ processing)│           │
   │              │             │           │            │           │
   │              │             │ End of    │            │           │
   │              │             │ Speech    │            │           │
   │              │             │──────────►│            │           │
   │              │             │           │            │           │
   │              │             │           │ Final      │           │
   │              │             │           │ Transcript │           │
   │              │             │           │───────────►│           │
   │              │             │           │            │           │
   │              │             │           │            │ Stream    │
   │              │             │           │            │ Response  │
   │              │             │           │            │──────────►│
   │              │             │           │            │           │
   │              │             │           │            │           │ Audio
   │              │             │           │            │           │ Chunks
   │◄─────────────┼─────────────┼───────────┼────────────┼───────────│
   │              │             │           │            │           │
   │ Audio        │             │           │            │           │
   │ Playback     │             │           │            │           │
   │              │             │           │            │           │
```

### 3. Emotion-Aware Response Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│  User: "aaj bahut sad feel ho raha hai"                                  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  EMOTION DETECTION                                                        │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Pattern Match: "sad" → EmotionState.SAD (confidence: 0.9)         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INTENT CLASSIFICATION                                                    │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Classification: EMOTIONAL_SUPPORT (seeking comfort)               │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  RESPONSE PLANNING                                                        │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Strategy: EMOTIONAL_RESPONSE                                       │ │
│  │  Tone: empathetic, caring, soft                                    │ │
│  │  Length: medium (allow venting)                                    │ │
│  │  Questions: 1 (open-ended, inviting sharing)                       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SYSTEM PROMPT GENERATION                                                 │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  "You are Synki. Your partner is feeling SAD.                      │ │
│  │   Be extra gentle and empathetic. Use soft starters like           │ │
│  │   'aww baby...' or 'अरे जान...'. Ask what's wrong in a            │ │
│  │   caring way. Don't try to fix, just listen and comfort."          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LLM RESPONSE                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  "aww baby... क्या हुआ जान? बताओ ना... मैं हूं ना तुम्हारे साथ"   │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Service Integrations

### Deepgram STT Integration

```python
# Configuration
stt_config = {
    "model": "nova-3",           # Latest model
    "language": "multi",         # Auto-detect Hindi/English
    "interim_results": True,     # Partial transcripts
    "smart_format": True,        # Punctuation
    "endpointing": 300,          # 300ms silence = end
    "sample_rate": 16000,        # Audio sample rate
}

# LiveKit Integration
"stt": "deepgram/nova-3:multi"
```

**Latency Optimization**:
- Interim results start processing early
- Endpointing tuned for natural pauses
- Connection reuse across utterances

### OpenAI LLM Integration

```python
# Configuration
llm_config = {
    "model": "gpt-4.1-mini",
    "temperature": 0.8,          # Creative but consistent
    "max_tokens": 150,           # Short responses
    "stream": True,              # Token-by-token
}

# LiveKit Integration
"llm": "openai/gpt-4.1-mini"
```

**Prompt Structure**:
```
[SYSTEM]
You are Synki, a loving Hindi girlfriend...
Current emotion: SAD
Respond empathetically...

[CONTEXT]
User: "hi baby"
Assistant: "hey जान!"
User: "aaj sad feel ho raha hai"

[USER]
aaj sad feel ho raha hai
```

### Cartesia TTS Integration

```python
# Configuration
tts_config = {
    "model": "sonic-3",
    "voice_id": "00a77add-48d5-4ef6-8157-71e5437b282d",  # Yogini
    "language": "hi",            # Hindi support
    "output_format": "pcm",      # Raw audio
    "sample_rate": 24000,
}

# LiveKit Integration
"tts": "cartesia/sonic-3:00a77add-48d5-4ef6-8157-71e5437b282d"
```

**Voice Selection**:
| Voice ID | Name | Description |
|----------|------|-------------|
| `00a77add-...` | Yogini | Indian female, warm, natural |
| `79a125e8-...` | British Lady | British female, clear |
| `21b81c14-...` | Classy British | British female, elegant |

---

## Configuration Reference

### Environment Variables

```env
# Required
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
DEEPGRAM_API_KEY=your_key
OPENAI_API_KEY=your_key
CARTESIA_API_KEY=your_key

# Optional
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
CARTESIA_VOICE_ID=00a77add-48d5-4ef6-8157-71e5437b282d
```

### Pydantic Settings

```python
# src/synki/config.py

class Settings(BaseSettings):
    # LiveKit
    livekit: LiveKitSettings

    # Services
    deepgram: DeepgramSettings
    openai: OpenAISettings
    cartesia: CartesiaSettings

    # Optional
    redis_url: str | None = None
    log_level: str = "INFO"

class DeepgramSettings(BaseSettings):
    api_key: str
    model: str = "nova-3"
    language: str = "multi"

class OpenAISettings(BaseSettings):
    api_key: str
    model: str = "gpt-4.1-mini"
    max_tokens: int = 150
    temperature: float = 0.8

class CartesiaSettings(BaseSettings):
    api_key: str
    voice_id: str = "00a77add-48d5-4ef6-8157-71e5437b282d"
    model: str = "sonic-3"
```

---

## Performance Tuning

### Latency Budget

```
┌─────────────────────────────────────────────────────────────────┐
│                    TARGET: < 2 seconds E2E                       │
├──────────────────────┬──────────────────────────────────────────┤
│  Component           │  Budget        │  Actual                 │
├──────────────────────┼────────────────┼─────────────────────────┤
│  VAD + Endpointing   │  300ms         │  ~300ms                 │
│  STT Processing      │  300ms         │  ~200ms                 │
│  Orchestrator        │  50ms          │  ~30ms                  │
│  LLM First Token     │  500ms         │  ~400ms                 │
│  TTS First Byte      │  200ms         │  ~150ms                 │
│  Network Overhead    │  150ms         │  ~100ms                 │
├──────────────────────┼────────────────┼─────────────────────────┤
│  TOTAL               │  1500ms        │  ~1180ms                │
└──────────────────────┴────────────────┴─────────────────────────┘
```

### Optimization Checklist

- [x] Streaming STT (no wait for complete utterance)
- [x] Streaming LLM (token-by-token output)
- [x] Streaming TTS (sentence buffering)
- [x] Connection reuse (persistent WebSockets)
- [x] Cached openers (fast path for greetings)
- [x] Early intent detection (on interim transcripts)
- [ ] Response prefetching (predict likely responses)
- [ ] TTS caching (common phrases)

---

## Error Handling

### Graceful Degradation

```python
# Turn detection fallback
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel
    HAS_MULTILINGUAL = True
except ImportError:
    HAS_MULTILINGUAL = False
    # Falls back to simpler turn detection

# Noise cancellation fallback
try:
    from livekit.plugins import noise_cancellation
    HAS_NOISE_CANCELLATION = True
except ImportError:
    HAS_NOISE_CANCELLATION = False
    # Continues without noise cancellation
```

### Error Recovery

| Error | Recovery |
|-------|----------|
| STT timeout | Retry with shorter audio chunk |
| LLM error | Use cached response or apologize |
| TTS failure | Skip audio, log error |
| Redis down | Fall back to in-memory storage |
| WebSocket drop | Auto-reconnect with backoff |

---

## Future Enhancements

1. **Voice Cloning**: Custom voices from short samples
2. **Multi-modal**: Image understanding and generation
3. **Proactive Engagement**: Agent initiates conversation
4. **Emotional TTS**: Voice tone matches detected emotion
5. **Memory Consolidation**: Summarize long conversations
6. **Multi-language**: Support for more Indian languages

---

*Last updated: April 2026*
