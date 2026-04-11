# 💕 Synki - Hindi AI Girlfriend Voice Companion

<div align="center">

![Synki Banner](https://img.shields.io/badge/Synki-AI%20Girlfriend-ff69b4?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)
![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**A real-time voice AI companion that speaks natural Hinglish with a warm, loving girlfriend personality**

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Configuration](#-configuration) • [API Reference](#-api-reference)

</div>

---

## 🎯 What is Synki?

Synki is a **Hindi girlfriend-style voice companion** that creates emotionally engaging conversations through real-time voice. Unlike generic voice assistants, Synki:

- 💬 Speaks natural **Hinglish** (Hindi in Devanagari + English)
- 💕 Maintains a **warm, caring, playful** girlfriend personality
- 🧠 Remembers your preferences and conversation history
- 😊 Detects emotions and adapts responses accordingly
- ⚡ Achieves **sub-second latency** through streaming pipelines

### Example Conversation

```
You: "aaj bahut thak gaya"
Synki: "aww baby, इतना थक गए? आज का दिन बहुत hectic रहा क्या? बताओ ना जान..."

You: "promotion mil gayi!"  
Synki: "अरे वाह! I'm so proud of you baby! मुझे पता था तुम कर लोगे! 🎉"
```

---

## ✨ Features

### 🎙️ Real-Time Voice Pipeline
- **Streaming STT** with Deepgram Nova-3 (Hindi + English)
- **Streaming LLM** with OpenAI GPT-4.1
- **Streaming TTS** with Cartesia Sonic-3 (Indian female voice)
- End-to-end latency: **~1.5-2 seconds**

### 💝 Girlfriend Personality
- Loving, affectionate, and emotionally supportive
- Uses pet names: "baby", "जान", "sweetheart", "मेरी जान"
- Adapts tone based on detected emotions
- Playful teasing and genuine care

### 🧠 Intelligent Orchestration
- **Emotion Detection**: Recognizes happiness, sadness, tiredness, frustration
- **Intent Classification**: Greetings, questions, emotional support, casual chat
- **Context Management**: Tracks conversation history and topics
- **Memory Service**: Remembers long-term facts about you

### 🌐 Production Ready
- WebRTC transport via LiveKit Cloud
- Scalable architecture with session management
- Redis-backed persistence (optional)
- Docker deployment support

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER DEVICE                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Web Browser / Mobile App                                            │   │
│  │  • Microphone capture                                                │   │
│  │  • Speaker playback                                                  │   │
│  │  • LiveKit Client SDK                                                │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │ WebRTC (Audio)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LIVEKIT CLOUD                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  LiveKit Room                                                        │   │
│  │  • User Audio Track (published)                                      │   │
│  │  • Agent Audio Track (subscribed by user)                            │   │
│  │  • Signaling & NAT Traversal                                         │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │ Subscribe/Publish
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SYNKI AGENT                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Voice Pipeline                                  │   │
│  │                                                                      │   │
│  │  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │   │
│  │  │ Deepgram │───►│ LLM      │───►│ Cartesia │───►│ Audio    │      │   │
│  │  │ STT      │    │ (GPT-4.1)│    │ TTS      │    │ Output   │      │   │
│  │  │          │    │          │    │          │    │          │      │   │
│  │  │ Hindi +  │    │ Hinglish │    │ Indian   │    │ WebRTC   │      │   │
│  │  │ English  │    │ Response │    │ Female   │    │ Stream   │      │   │
│  │  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │   │
│  │       │               ▲                                             │   │
│  │       ▼               │                                             │   │
│  │  ┌────────────────────┴───────────────────────────────────────┐    │   │
│  │  │                    ORCHESTRATOR                             │    │   │
│  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐              │    │   │
│  │  │  │  Session   │ │  Emotion   │ │   Intent   │              │    │   │
│  │  │  │  Manager   │ │  Detector  │ │  Detector  │              │    │   │
│  │  │  └────────────┘ └────────────┘ └────────────┘              │    │   │
│  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐              │    │   │
│  │  │  │  Context   │ │  Persona   │ │  Response  │              │    │   │
│  │  │  │  Manager   │ │  Engine    │ │  Planner   │              │    │   │
│  │  │  └────────────┘ └────────────┘ └────────────┘              │    │   │
│  │  │  ┌────────────┐                                            │    │   │
│  │  │  │  Memory    │ (Redis - Optional)                         │    │   │
│  │  │  │  Service   │                                            │    │   │
│  │  │  └────────────┘                                            │    │   │
│  │  └────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Transport** | LiveKit Cloud | WebRTC rooms, audio streaming |
| **STT** | Deepgram Nova-3 | Hindi/English speech-to-text |
| **LLM** | OpenAI GPT-4.1-mini | Response generation |
| **TTS** | Cartesia Sonic-3 | Indian female voice synthesis |
| **Runtime** | Python 3.10+ | Agent server |
| **Package Manager** | uv | Fast dependency management |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- API keys for: LiveKit, Deepgram, OpenAI, Cartesia

### Installation

```bash
# Clone the repository
git clone https://github.com/8789pranav/synki.git
cd synki

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env.local
```

### Configuration

Edit `.env.local` with your API keys:

```env
# LiveKit (get from https://cloud.livekit.io)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret

# Deepgram (get from https://deepgram.com)
DEEPGRAM_API_KEY=your_deepgram_key

# OpenAI (get from https://platform.openai.com)
OPENAI_API_KEY=your_openai_key

# Cartesia (get from https://cartesia.ai)
CARTESIA_API_KEY=your_cartesia_key
```

### Running the Agent

```bash
# Development mode (with auto-reload)
uv run python -m synki.agent dev

# Production mode
uv run python -m synki.agent start
```

### Testing with Frontend

1. Start the API server: `uv run python api_server.py`
2. Start the agent: `uv run python -m synki.agent dev`
3. Open `http://localhost:8000` in a browser
4. Login and click "Connect" to talk to Synki!

---

## 📁 Project Structure

```
synki/
├── api_server.py               # 🚀 FastAPI server (token + API)
├── pyproject.toml              # Dependencies
├── .env.local                  # API keys (gitignored)
├── .env.example                # Environment template
│
├── frontend/                   # Web UI
│   └── app.html                # Main Synki app
│
├── src/synki/                  # Core library
│   ├── config.py               # Pydantic settings
│   ├── models.py               # Data models
│   │
│   ├── agent/                  # LiveKit agent
│   │   ├── __main__.py         # CLI entry
│   │   └── companion_agent.py  # Agent implementation
│   │
│   ├── orchestrator/           # AI brain
│   │   ├── orchestrator.py     # Main coordinator
│   │   ├── session_manager.py  # Session state
│   │   ├── context_manager.py  # Conversation context
│   │   ├── memory_service.py   # Long-term memory
│   │   ├── emotion_detector.py # Emotion detection
│   │   ├── intent_detector.py  # Intent classification
│   │   ├── persona_engine.py   # GF personality
│   │   └── response_planner.py # Response strategy
│   │
│   └── services/               # External integrations
│       ├── stt_service.py      # Deepgram
│       ├── llm_service.py      # OpenAI
│       └── tts_service.py      # Cartesia
│
├── tests/                      # Unit tests
│   ├── conftest.py
│   ├── test_emotion_detector.py
│   ├── test_intent_detector.py
│   └── test_persona_engine.py
│
├── docs/                       # Documentation
│   └── architecture.md         # Detailed architecture
│
├── Dockerfile                  # Container deployment
└── README.md                   # This file
```

---

## ⚙️ Configuration

### Voice Configuration

The default voice is **Yogini** - an Indian female voice from Cartesia. To change:

```python
# In agent.py
"tts": "cartesia/sonic-3:YOUR_VOICE_ID"
```

Available voice options:
- `00a77add-48d5-4ef6-8157-71e5437b282d` - Yogini (Indian female) ✓
- `79a125e8-cd45-4c13-8a67-188112f4dd22` - British Lady
- `21b81c14-f85b-436d-aff5-43f2e788ecf8` - Classy British Woman

### Personality Customization

Edit the `instructions` in `agent.py` to customize personality:

```python
instructions = """You are Synki, a loving girlfriend..."""
```

### Language Settings

Synki outputs Hindi in **Devanagari script** for proper TTS pronunciation:

```
✓ "aww baby, कैसे हो तुम?"
✗ "aww baby, kaise ho tum?"
```

---

## 🔧 API Reference

### Core Models

```python
# Emotion States
class EmotionState(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    TIRED = "tired"
    FRUSTRATED = "frustrated"
    EXCITED = "excited"
    LOVING = "loving"

# Intent Types
class IntentType(Enum):
    GREETING = "greeting"
    FAREWELL = "farewell"
    QUESTION = "question"
    STATEMENT = "statement"
    EMOTIONAL_SUPPORT = "emotional_support"
    CASUAL_CHAT = "casual_chat"

# Response Strategies
class ResponseStrategy(Enum):
    CACHED_OPENER = "cached_opener"
    SHORT_RESPONSE = "short_response"
    FULL_RESPONSE = "full_response"
    EMOTIONAL_RESPONSE = "emotional_response"
    PLAYFUL_TEASE = "playful_tease"
```

### Orchestrator Usage

```python
from synki.orchestrator import Orchestrator
from synki.models import TranscriptEvent

orchestrator = Orchestrator()

# Create session
session = await orchestrator.session_manager.create_session(user_id="user123")

# Process transcript
transcript = TranscriptEvent(text="hello baby", is_final=True)
llm_input = await orchestrator.process_transcript(session.id, transcript)

# Generate response
if llm_input:
    response = await llm_service.generate_stream(
        system_prompt=llm_input.system_prompt,
        user_message=llm_input.user_message,
        context=llm_input.context_messages,
    )
```

---

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/synki

# Run specific test
uv run pytest tests/test_emotion_detector.py -v
```

---

## 🐳 Docker Deployment

```bash
# Build image
docker build -t synki .

# Run container
docker run -d \
  --env-file .env.local \
  -p 8080:8080 \
  synki
```

---

## 📊 Latency Optimization

| Stage | Target | Actual |
|-------|--------|--------|
| STT (Deepgram) | <300ms | ~200ms |
| Orchestrator | <50ms | ~30ms |
| LLM First Token | <500ms | ~400ms |
| TTS First Byte | <200ms | ~150ms |
| **End-to-End** | **<1.5s** | **~1.7s** |

### Optimization Techniques

1. **Streaming Everything**: STT → LLM → TTS all stream
2. **Interim Processing**: Start detecting intent on partial transcripts
3. **Sentence Buffering**: Send complete sentences to TTS for natural prosody
4. **Connection Reuse**: Keep WebSocket connections alive
5. **Fast Path**: Cached responses for common greetings

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- [LiveKit](https://livekit.io) - Real-time communication infrastructure
- [Deepgram](https://deepgram.com) - Speech-to-text AI
- [OpenAI](https://openai.com) - Language model
- [Cartesia](https://cartesia.ai) - Text-to-speech

---

<div align="center">

**Made with 💕 for real conversations**

[Report Bug](https://github.com/8789pranav/synki/issues) • [Request Feature](https://github.com/8789pranav/synki/issues)

</div>
