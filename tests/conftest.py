"""
Synki Test Configuration
"""

import pytest


@pytest.fixture
def sample_transcript():
    """Sample transcript for testing."""
    from synki.models import TranscriptEvent
    
    return TranscriptEvent(
        session_id="test_session_1",
        type="final_transcript",
        text="aaj bahut tired feel ho raha hai",
        is_final=True,
        speech_final=True,
        confidence=0.95,
    )


@pytest.fixture
def sample_session():
    """Sample session state for testing."""
    from synki.models import SessionState, PersonaProfile, ContextPacket
    
    return SessionState(
        session_id="test_session_1",
        user_id="test_user_1",
        room_name="test_room_1",
        persona=PersonaProfile(),
        context=ContextPacket(),
    )


@pytest.fixture
def orchestrator():
    """Orchestrator instance for testing."""
    from synki.orchestrator import Orchestrator
    
    return Orchestrator()
