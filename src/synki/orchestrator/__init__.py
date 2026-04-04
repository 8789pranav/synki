"""
Synki Orchestrator - Core Module

The AI Orchestrator is the brain of the companion. It handles:
- Intent and emotion detection
- Context management
- Memory service integration
- Persona/style engine
- Response strategy selection
- Safety layer
- Layered memory (L0-L6)
- Entity extraction and thread management
- Anti-repetition
"""

from .context_manager import ContextManager
from .emotion_detector import EmotionDetector
from .intent_detector import IntentDetector
from .memory_service import MemoryService
from .persona_engine import PersonaEngine
from .response_planner import ResponsePlanner
from .session_manager import SessionManager
from .orchestrator import Orchestrator

# New layered memory components
from .layered_memory import (
    LayeredMemoryService,
    TurnBuffer,
    SessionState as LayeredSessionState,
    ConversationThread,
    MemoryFact,
    Entity,
    EntityType,
    MemoryCategory,
    ThreadType,
)
from .entity_extractor import EntityExtractor
from .thread_manager import ThreadManager
from .anti_repetition import AntiRepetitionChecker
from .summary_generator import SummaryGenerator
from .proactive_memory import ProactiveMemoryPrompter, MemoryPrompt, MemoryTopic
from .enhanced_orchestrator import EnhancedOrchestrator, create_orchestrator

__all__ = [
    # Original components
    "ContextManager",
    "EmotionDetector",
    "IntentDetector",
    "MemoryService",
    "PersonaEngine",
    "ResponsePlanner",
    "SessionManager",
    "Orchestrator",
    
    # Enhanced orchestrator
    "EnhancedOrchestrator",
    "create_orchestrator",
    
    # Layered memory
    "LayeredMemoryService",
    "TurnBuffer",
    "LayeredSessionState",
    "ConversationThread",
    "MemoryFact",
    "Entity",
    "EntityType",
    "MemoryCategory",
    "ThreadType",
    
    # New components
    "EntityExtractor",
    "ThreadManager",
    "AntiRepetitionChecker",
    "SummaryGenerator",
    "ProactiveMemoryPrompter",
    "MemoryPrompt",
    "MemoryTopic",
]
