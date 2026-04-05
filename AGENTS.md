# AGENTS.md - Synki Voice Companion

This file helps AI coding agents understand the Synki codebase.

## Project Overview

Synki is a Hindi GF-style voice companion using:
- **LiveKit** for WebRTC transport
- **Deepgram** for streaming STT
- **OpenAI** for LLM generation
- **Cartesia** for streaming TTS

## Key Concepts

### The Voice Pipeline
```
User Audio → Deepgram STT → Orchestrator → OpenAI LLM → Cartesia TTS → User Audio
```

### Proactive GF System
```
Scheduler → Decision Engine → Message Generator → Push Notification → User
                ↓
        (Time + Mood + History)
```

**Proactive Features:**
- Morning greetings, lunch check-ins, evening calls
- Random "miss you" messages
- Incoming call UI (rings, user picks up)
- Smart timing based on user's mood and history

### Orchestrator Components
- `SessionManager`: Manages conversation sessions
- `ContextManager`: Tracks recent messages and topics
- `ContextBuilder`: Smart context with anti-repetition, conversation flow
- `MemoryService`: Long-term user facts (Redis)
- `EmotionDetector`: Pattern-based emotion detection
- `IntentDetector`: Classifies user input
- `PersonaEngine`: Manages GF personality
- `ResponsePlanner`: Decides response strategy

### Proactive Components (NEW)
- `DecisionEngine`: Decides when/how to contact user
- `MessageGenerator`: Natural Hinglish messages
- `ProactiveScheduler`: Background job for triggering contacts

## File Structure

```
src/synki/
├── agent/                  # LiveKit agent
│   └── companion_agent.py  # Main entry point
├── orchestrator/           # AI orchestration
│   ├── orchestrator.py     # Main coordinator
│   ├── context_builder.py  # Smart context builder
│   ├── persona_engine.py   # Personality management
│   └── ...
├── proactive/              # Proactive GF system (NEW)
│   ├── decision_engine.py  # When/how to contact
│   ├── message_generator.py # Natural messages
│   ├── scheduler.py        # Background scheduler
│   └── api.py             # API endpoints
├── services/               # External APIs
│   ├── stt_service.py      # Deepgram
│   ├── llm_service.py      # OpenAI
│   └── tts_service.py      # Cartesia
├── config.py               # Pydantic settings
└── models.py               # Data models
```

## Important Models

### PersonaProfile
```python
PersonaProfile(
    mode=PersonaMode.GIRLFRIEND,
    language_style=LanguageStyle.HINGLISH,
    tone="soft, caring, slightly playful",
    question_limit=1,
)
```

### SessionState
Tracks current conversation state, context, and persona.

### LLMInputPacket
Prepared input for LLM generation including persona, context, and goals.

## Running the Agent

```bash
# Development
uv run python -m synki.agent dev

# Production
uv run python -m synki.agent start

# Run proactive scheduler (cron job)
python -m synki.proactive.scheduler
```

## Testing

```bash
uv run pytest
```

## Key Design Decisions

1. **Streaming Everything**: STT, LLM, and TTS all stream for low latency
2. **Sentence Buffering**: LLM output buffered until complete sentences
3. **Fast Path**: Greetings use cached responses for <400ms latency
4. **Anti-Repetition**: Track recent phrases to avoid repetition
5. **Hinglish**: Mix of Hindi and English in romanized script

## Common Tasks

### Adding New Emotions
Edit `orchestrator/emotion_detector.py`:
```python
EMOTION_PATTERNS[EmotionState.NEW_EMOTION] = [
    r"\b(pattern1|pattern2)\b",
]
```

### Changing Persona
Edit `PersonaProfile` in `models.py` or pass to `CompanionAssistant`.

### Adding Memory Facts
The memory service automatically learns from conversation. To add new fact types, edit `memory_service.py`.
