# Synki - Hindi GF-style Voice Companion

A real-time voice AI companion built with modern voice AI infrastructure:

- **LiveKit** - Realtime WebRTC transport layer
- **Deepgram** - Streaming speech-to-text with interim results
- **OpenAI** - LLM for context-aware responses
- **Cartesia** - Ultra-low-latency streaming text-to-speech

## 🎯 What is Synki?

Synki is a Hindi girlfriend-style voice companion that maintains personality, context, and memory across conversations. Unlike generic voice bots, Synki:

- Speaks natural **Hinglish** (mix of Hindi and English)
- Maintains a **warm, caring, playful** personality
- Remembers user preferences and conversation history
- Detects emotions and adapts responses accordingly
- Achieves **sub-second latency** through streaming pipelines

## 🏗️ Architecture

```
+--------------------------- CLIENT ---------------------------+
| Mobile App / Web App                                         |
| - Mic capture                                                |
| - Speaker playback                                           |
+------------------------------+-------------------------------+
                               |
                               v
+---------------------- LIVEKIT / WEBRTC ----------------------+
| LiveKit Room                                                 |
| - User published audio track                                 |
| - AI agent subscribed to user audio                          |
| - AI agent publishes reply audio track                       |
+------------------------------+-------------------------------+
                               |
                               v
+--------------------- AI ORCHESTRATOR ------------------------+
| Session manager                                              |
| Intent + emotion detector                                    |
| Context manager                                              |
| Memory service                                               |
| Persona / style engine                                       |
| Response planner                                             |
+-----------+----------------------+---------------------------+
            |                      |
            v                      v
+-------------------+     +--------------------+
| Deepgram STT      |     | OpenAI LLM         |
| - streaming audio |     | - streaming text   |
| - interim text    |     | - Hinglish style   |
+-------------------+     +--------------------+
            \                      /
             \                    /
              v                  v
             +----------------------+
             | Response planner     |
             | - opener selection   |
             | - anti-repetition    |
             +----------------------+
                        |
                        v
               +------------------+
               | Cartesia TTS     |
               | - WebSocket TTS  |
               | - streaming out  |
               +------------------+
                        |
                        v
+---------------------- LIVEKIT / WEBRTC ----------------------+
| AI published audio back into room                            |
+--------------------------------------------------------------+
```

## 📁 Project Structure

```
synki/
├── src/
│   └── synki/
│       ├── __init__.py
│       ├── config.py              # Pydantic settings
│       ├── models.py              # Data models
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── __main__.py        # CLI entry point
│       │   └── companion_agent.py # LiveKit agent
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── orchestrator.py    # Main coordinator
│       │   ├── session_manager.py # Session state
│       │   ├── context_manager.py # Conversation context
│       │   ├── memory_service.py  # Long-term memory
│       │   ├── emotion_detector.py
│       │   ├── intent_detector.py
│       │   ├── persona_engine.py  # GF personality
│       │   └── response_planner.py
│       └── services/
│           ├── __init__.py
│           ├── stt_service.py     # Deepgram integration
│           ├── llm_service.py     # OpenAI integration
│           └── tts_service.py     # Cartesia integration
├── tests/
├── pyproject.toml
├── .env.example
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- [LiveKit CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/)
- API keys for: LiveKit Cloud, Deepgram, OpenAI, Cartesia

### Installation

1. **Clone and setup:**
```bash
git clone <repository>
cd synki
uv sync
```

2. **Configure environment:**
```bash
cp .env.example .env.local
# Edit .env.local with your API keys
```

3. **Download model files:**
```bash
uv run python -m synki.agent download-files
```

4. **Run in development mode:**
```bash
uv run python -m synki.agent dev
```

5. **Connect to your agent:**
- Open the LiveKit Agents Playground
- Or use the provided chat link from the CLI output

### Environment Variables

```env
# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Deepgram (STT)
DEEPGRAM_API_KEY=your_deepgram_key

# OpenAI (LLM)
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4.1-mini

# Cartesia (TTS)
CARTESIA_API_KEY=your_cartesia_key
CARTESIA_VOICE_ID=your_voice_id

# Redis (optional, for persistence)
REDIS_URL=redis://localhost:6379/0
```

## 💬 Persona Configuration

Synki's personality is configured through the `PersonaProfile`:

```python
from synki.models import PersonaProfile, PersonaMode, LanguageStyle

persona = PersonaProfile(
    mode=PersonaMode.GIRLFRIEND,
    language_style=LanguageStyle.HINGLISH,
    tone="soft, caring, slightly playful",
    question_limit=1,  # Max questions per response
    emoji_level="low",
    avoid=[
        "formal Hindi",
        "robotic phrasing",
        "too many questions",
        "repetitive phrases",
    ],
)
```

## 🧠 How It Works

### 1. Speech-to-Text (Deepgram)
- Streaming STT with interim results
- Hindi + English language support
- 300ms endpointing for natural turn detection
- Partial transcripts enable fast-path responses

### 2. Orchestration
The orchestrator coordinates all intelligence:
- **Intent Detection**: Greeting, question, emotional support, etc.
- **Emotion Detection**: Happy, sad, tired, stressed, etc.
- **Context Management**: Recent messages, current topic
- **Memory Service**: Long-term user facts
- **Response Planning**: Strategy selection, opener choice

### 3. LLM Generation (OpenAI)
- Streaming responses for low latency
- Persona-injected system prompts
- Context-aware generation
- Anti-repetition via phrase tracking

### 4. Text-to-Speech (Cartesia)
- WebSocket streaming with contexts
- Incremental text input (doesn't wait for full response)
- Seamless prosody across text chunks
- 90ms time-to-first-byte

### 5. Low-Latency Pipeline
```
User finishes speaking
    ↓ (300ms endpointing)
Final transcript arrives
    ↓ (immediate)
Intent/emotion detected
    ↓ (fast-path check)
    ├── Quick response? → Direct to TTS
    └── Full response? → Continue below
    ↓
LLM starts streaming
    ↓ (first token ~200ms)
First sentence complete
    ↓ (immediate)
TTS starts generating
    ↓ (90ms TTFB)
User starts hearing response
```

**Total latency: ~600-800ms** from user stop speaking to hearing response

## 🎭 Response Examples

**User says:** "aaj bahut tired feel ho raha hai"

**Synki responds:** "hmm... sounds like a long day yaar. kya hua aaj?"

---

**User says:** "office mein meeting thi bohot stressful"

**Synki responds:** "arre yaar, stressful meetings are the worst. ab relax karo thoda."

---

**User says:** "hi!"

**Synki responds:** "hiii! kaise ho aaj? batao kya chal raha hai?"

## 🧪 Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=synki

# Type checking
uv run mypy src/synki

# Linting
uv run ruff check src/synki
```

## 📦 Deployment

### LiveKit Cloud

```bash
# Register and deploy agent
lk agent create

# Check deployment status
lk agent list
```

### Self-Hosted

```bash
# Build container
docker build -t synki-agent .

# Run with env file
docker run --env-file .env.local synki-agent
```

## 🔧 Customization

### Adding New Personas

```python
# In orchestrator/persona_engine.py
PERSONAS = {
    "girlfriend": PersonaProfile(
        mode=PersonaMode.GIRLFRIEND,
        tone="soft, caring, slightly playful",
        # ...
    ),
    "friend": PersonaProfile(
        mode=PersonaMode.FRIEND,
        tone="casual, fun, supportive",
        # ...
    ),
}
```

### Custom Emotion Patterns

```python
# In orchestrator/emotion_detector.py
EMOTION_PATTERNS[EmotionState.HAPPY].extend([
    r"\b(your_custom_happy_word)\b",
])
```

### Memory Facts

The memory service learns:
- User's name
- Sleep patterns
- Common emotional states
- Interests and topics
- Preferred language style

## 📚 API Reference

### Orchestrator

```python
from synki.orchestrator import Orchestrator

orch = Orchestrator()

# Create session
session = await orch.create_session(user_id, room_name)

# Process transcript
llm_packet = await orch.process_transcript(session_id, transcript)

# Get system prompt for LLM
prompt = orch.get_system_prompt(session, emotion, memory_facts)
```

### Services

```python
from synki.services import DeepgramSTTService, OpenAILLMService, CartesiaTTSService

# STT
stt = DeepgramSTTService()
await stt.start_stream(session_id, on_transcript_callback)
await stt.send_audio(audio_bytes)

# LLM
llm = OpenAILLMService()
async for chunk in llm.generate_stream(system_prompt, user_message):
    # Process streaming tokens

# TTS
tts = CartesiaTTSService()
async for audio in tts.synthesize_stream(text_iterator):
    # Play audio chunks
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- [LiveKit](https://livekit.io/) - Realtime communication platform
- [Deepgram](https://deepgram.com/) - Speech recognition
- [OpenAI](https://openai.com/) - Language models
- [Cartesia](https://cartesia.ai/) - Text-to-speech

---

Built with ❤️ for natural voice AI conversations.
