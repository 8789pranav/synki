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

### Orchestrator Components
- `SessionManager`: Manages conversation sessions
- `ContextManager`: Tracks recent messages and topics
- `MemoryService`: Long-term user facts (Redis)
- `EmotionDetector`: Pattern-based emotion detection
- `IntentDetector`: Classifies user input
- `PersonaEngine`: Manages GF personality
- `ResponsePlanner`: Decides response strategy

## File Structure

```
src/synki/
├── agent/                  # LiveKit agent
│   └── companion_agent.py  # Main entry point
├── orchestrator/           # AI orchestration
│   ├── orchestrator.py     # Main coordinator
│   ├── persona_engine.py   # Personality management
│   └── ...
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
