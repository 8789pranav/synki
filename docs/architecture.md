# Synki Architecture Documentation

## Overview

Synki is a real-time voice AI companion designed for natural, low-latency conversations in Hinglish (Hindi + English). This document describes the system architecture and design decisions.

## Design Principles

1. **Low Latency First**: Every component is chosen and configured for minimal latency
2. **Streaming Everything**: No waiting for complete results - stream STT, LLM, and TTS
3. **Personality Consistency**: Maintain character through orchestration, not just prompts
4. **Anti-Repetition**: Track recent phrases to avoid robotic repetition
5. **Context Awareness**: Remember both short-term conversation and long-term facts

## Component Architecture

### Transport Layer: LiveKit

LiveKit provides the WebRTC infrastructure:

```
┌─────────────────┐    WebRTC    ┌─────────────────┐
│   User Client   │◄────────────►│   LiveKit Room  │
│   (Web/Mobile)  │              │                 │
└─────────────────┘              └────────┬────────┘
                                          │
                                          │ Subscribe/Publish
                                          │
                                 ┌────────▼────────┐
                                 │   AI Agent      │
                                 │   (Synki)       │
                                 └─────────────────┘
```

**Why LiveKit?**
- Handles WebRTC complexity (NAT, ICE, DTLS)
- Built-in support for AI agents as room participants
- Scales to production without infrastructure changes
- Supports both cloud and self-hosted deployments

### STT Layer: Deepgram

Configuration for low-latency transcription:

```python
stt = deepgram.STT(
    model="nova-3",           # Latest, fastest model
    language="hi",            # Hindi with English support
    interim_results=True,     # Get partial transcripts
    smart_format=True,        # Punctuation, capitalization
    endpointing=300,          # 300ms silence = end of utterance
)
```

**Key Features Used:**
- **Interim Results**: Partial transcripts while user is still speaking
- **Endpointing**: Automatic detection of speech completion
- **Smart Format**: Clean, readable transcripts

**Latency Optimization:**
```
User speaking: ──────────────────►
                     │    │    │
              interim interim final
                     │    │    │
                     ▼    ▼    ▼
Processing starts early, not at the end
```

### Orchestrator Layer

The orchestrator is the "brain" that maintains personality and context:

```
┌──────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │   Session    │  │   Context    │                 │
│  │   Manager    │  │   Manager    │                 │
│  └──────────────┘  └──────────────┘                 │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │   Emotion    │  │   Intent     │                 │
│  │   Detector   │  │   Detector   │                 │
│  └──────────────┘  └──────────────┘                 │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │   Persona    │  │   Response   │                 │
│  │   Engine     │  │   Planner    │                 │
│  └──────────────┘  └──────────────┘                 │
│                                                      │
│  ┌──────────────┐                                   │
│  │   Memory     │                                   │
│  │   Service    │                                   │
│  └──────────────┘                                   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Session Manager**
- Creates and tracks conversation sessions
- Persists state to Redis (optional)
- Manages session lifecycle

**Context Manager**
- Tracks recent messages (last 5)
- Detects current topic
- Builds compact context for LLM

**Emotion Detector**
Pattern-based detection for both Hindi and English:
```python
EmotionState.TIRED: [
    r"\b(tired|thak|thaki|exhausted|sleepy|neend)\b",
    r"(😴|🥱|😩)",
]
```

**Intent Detector**
Classifies user input:
- GREETING, FAREWELL
- QUESTION, STATEMENT
- EMOTIONAL_SUPPORT
- CASUAL_CHAT

**Persona Engine**
- Manages GF personality configuration
- Generates system prompts
- Selects appropriate openers
- Applies style rules

**Response Planner**
Decides response strategy:
```python
ResponseStrategy.CACHED_OPENER    # Fast, pre-defined response
ResponseStrategy.SHORT_RESPONSE   # 1-2 sentences
ResponseStrategy.FULL_RESPONSE    # Complete LLM response
ResponseStrategy.EMOTIONAL_RESPONSE
ResponseStrategy.PLAYFUL_TEASE
```

**Memory Service**
Long-term facts about the user:
```python
LongTermMemory(
    name="Raj",
    sleep_pattern="late sleeper",
    common_states=["work_stress"],
    interests=["movies", "music"],
    preferred_language=LanguageStyle.HINGLISH,
)
```

### LLM Layer: OpenAI

Streaming generation with persona injection:

```python
# System prompt includes:
# - Personality description
# - Language style rules (Hinglish)
# - Response constraints (1-3 sentences)
# - User-specific memory facts
# - Current emotional context

async for chunk in llm.generate_stream(system_prompt, user_message):
    # Feed to TTS immediately
    pass
```

**Sentence Buffering**
For natural TTS, we buffer LLM output until complete sentences:
```python
class SentenceBuffer:
    SENTENCE_ENDINGS = {'.', '!', '?', '।'}  # Include Hindi danda
    
    def add(self, text: str) -> list[str]:
        # Returns complete sentences only
```

### TTS Layer: Cartesia

Streaming WebSocket TTS with contexts:

```python
async with client.tts.websocket() as ws:
    ctx = ws.context(
        model_id="sonic-3",
        voice={"mode": "id", "id": voice_id},
    )
    
    # Push text incrementally
    for sentence in sentences:
        ctx.push(sentence)
    
    ctx.no_more_inputs()
    
    # Receive audio as it's generated
    async for response in ctx.receive():
        yield response.audio
```

**Context Streaming**
Cartesia's "contexts" allow:
- Pushing text before knowing the full response
- Maintaining prosody across chunks
- Starting TTS before LLM completes

## Data Flow

### Happy Path (Full Response)

```
1. User speaks "aaj bahut tired feel ho raha hai"
   │
2. Deepgram streams transcription
   │ ├── interim: "aaj bahut"
   │ ├── interim: "aaj bahut tired"
   │ └── final: "aaj bahut tired feel ho raha hai"
   │
3. Orchestrator processes final transcript
   │ ├── Emotion: TIRED (confidence: 0.8)
   │ ├── Intent: STATEMENT
   │ ├── Topic: work_stress
   │ └── Strategy: EMOTIONAL_RESPONSE
   │
4. Response planner generates goal
   │ └── "Be empathetic, acknowledge tiredness, don't ask questions"
   │
5. LLM generates streaming response
   │ ├── "hmm..."
   │ ├── " sounds like"
   │ ├── " a long"
   │ ├── " day yaar."
   │ └── [end]
   │
6. Sentence buffer collects: "hmm... sounds like a long day yaar."
   │
7. Cartesia synthesizes with soft/caring emotion
   │
8. Audio streams back to user via LiveKit
```

### Fast Path (Cached Response)

```
1. User speaks "hi!"
   │
2. Deepgram returns final: "hi!"
   │
3. Orchestrator detects:
   │ ├── Intent: GREETING (confidence: 0.9)
   │ └── Strategy: CACHED_OPENER
   │
4. Response planner returns cached:
   │ └── "hiii! kaise ho aaj?"
   │
5. Direct to TTS (skip LLM)
   │
6. Audio streams back
   
Total latency: ~300-400ms
```

## Latency Budget

| Component | Target | Notes |
|-----------|--------|-------|
| User speaks | 0ms | Start |
| Endpointing | 300ms | Configurable |
| Orchestrator | <50ms | Local processing |
| LLM TTFT | ~200ms | Time to first token |
| Sentence buffer | ~100ms | Depends on LLM speed |
| TTS TTFB | 90ms | Cartesia Sonic |
| Network RTT | ~50ms | LiveKit optimized |
| **Total** | **~800ms** | User stop → audio starts |

## Anti-Repetition System

Problem: LLMs tend to repeat similar phrases.

Solution: Track and avoid recent phrases:

```python
# Session tracks recent phrases
session.recent_phrases = [
    "hmm... sounds tough",
    "acha... I understand",
    "poor you yaar",
]

# Response planner checks
if persona.check_for_repetition(response, recent_phrases):
    # Regenerate or modify
```

## Memory System

### Short-term (Session)
- Last 5 user messages
- Last 5 assistant messages
- Current topic
- Turn count

### Long-term (Redis)
- User name/nickname
- Sleep patterns
- Common emotional states
- Interests
- Important dates

### Learning
```python
# Automatically learn from conversation
async def learn_from_conversation(user_id, text, topic):
    # Extract sleep patterns
    if "late" in text and "sleep" in text:
        memory.sleep_pattern = "late sleeper"
    
    # Extract name
    if "mera naam" in text:
        memory.name = extract_name(text)
```

## Scaling Considerations

### Horizontal Scaling
- Agents are stateless (state in Redis)
- LiveKit Cloud handles agent dispatch
- Multiple agent instances per project

### Resource Usage
- Memory: ~100MB per agent instance
- CPU: Minimal (I/O bound)
- Network: ~100kbps per active session

### Redis Schema
```
session:{session_id} -> SessionState JSON (TTL: 1 hour)
memory:{user_id} -> LongTermMemory JSON (TTL: 30 days)
```

## Error Handling

### STT Errors
- Fallback to asking user to repeat
- Log and continue session

### LLM Errors
- Retry with exponential backoff
- Fallback to cached response

### TTS Errors
- Retry connection
- Fallback to system TTS if available

## Security

### API Keys
- Never committed to repo
- Loaded from environment
- Rotated regularly

### User Data
- Transcripts not stored permanently
- Memory data encrypted in Redis
- GDPR compliance considerations

## Future Enhancements

1. **Voice Cloning**: Custom voice training for more natural TTS
2. **Emotion in TTS**: Dynamic voice emotion based on context
3. **Multi-modal**: Add video avatar support
4. **Proactive**: Agent initiates based on time/context
5. **Multi-language**: Support for more Indian languages

## References

- [LiveKit Agents Docs](https://docs.livekit.io/agents/)
- [Deepgram Streaming API](https://developers.deepgram.com/docs/streaming)
- [Cartesia TTS WebSocket](https://docs.cartesia.ai/api-reference/tts/websocket)
- [OpenAI Streaming](https://platform.openai.com/docs/api-reference/streaming)
