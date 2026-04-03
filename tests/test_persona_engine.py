"""
Tests for persona engine.
"""

import pytest

from synki.models import EmotionState, IntentType, LanguageStyle, PersonaMode, PersonaProfile
from synki.orchestrator.persona_engine import PersonaEngine


class TestPersonaEngine:
    """Test persona engine functionality."""
    
    @pytest.fixture
    def engine(self):
        return PersonaEngine()
    
    @pytest.fixture
    def custom_persona(self):
        return PersonaProfile(
            mode=PersonaMode.GIRLFRIEND,
            language_style=LanguageStyle.HINGLISH,
            tone="warm and caring",
            question_limit=1,
        )
    
    def test_get_opener_neutral(self, engine):
        """Test getting opener for neutral emotion."""
        opener = engine.get_opener(EmotionState.NEUTRAL)
        assert opener in PersonaEngine.OPENERS[EmotionState.NEUTRAL]
    
    def test_get_opener_happy(self, engine):
        """Test getting opener for happy emotion."""
        opener = engine.get_opener(EmotionState.HAPPY)
        assert opener in PersonaEngine.OPENERS[EmotionState.HAPPY]
    
    def test_opener_variation(self, engine):
        """Test that openers vary (anti-repetition)."""
        openers = [engine.get_opener(EmotionState.NEUTRAL) for _ in range(10)]
        # Should have at least 2 unique openers in 10 attempts
        assert len(set(openers)) >= 2
    
    def test_system_prompt_contains_persona(self, engine, custom_persona):
        """Test that system prompt includes persona settings."""
        engine.profile = custom_persona
        prompt = engine.get_system_prompt()
        
        assert "girlfriend" in prompt.lower()
        assert "hinglish" in prompt.lower() or "hindi" in prompt.lower()
    
    def test_system_prompt_with_user_name(self, engine):
        """Test system prompt with user name."""
        prompt = engine.get_system_prompt(user_name="Raj")
        assert "Raj" in prompt
    
    def test_system_prompt_with_memory_facts(self, engine):
        """Test system prompt with memory facts."""
        facts = ["User is a late sleeper", "User likes movies"]
        prompt = engine.get_system_prompt(memory_facts=facts)
        
        assert "late sleeper" in prompt
        assert "movies" in prompt
    
    def test_format_response_goal(self, engine):
        """Test response goal formatting."""
        goal = engine.format_response_goal(
            IntentType.GREETING,
            EmotionState.HAPPY,
            include_question=True,
        )
        
        assert "Hinglish" in goal
        assert "question" in goal.lower()
    
    def test_should_use_teasing_negative_emotion(self, engine):
        """Test that teasing is disabled for negative emotions."""
        assert not engine.should_use_teasing(EmotionState.SAD, IntentType.CASUAL_CHAT)
        assert not engine.should_use_teasing(EmotionState.STRESSED, IntentType.CASUAL_CHAT)
        assert not engine.should_use_teasing(EmotionState.ANXIOUS, IntentType.CASUAL_CHAT)
    
    def test_check_repetition_exact_match(self, engine):
        """Test repetition check for exact matches."""
        recent = ["hello there!", "how are you?"]
        assert engine.check_for_repetition("hello there!", recent)
        assert not engine.check_for_repetition("something new", recent)
    
    def test_check_repetition_partial_overlap(self, engine):
        """Test repetition check for high overlap."""
        recent = ["hmm sounds like a tough day yaar"]
        # High overlap should be detected
        assert engine.check_for_repetition("hmm sounds like a tough day", recent)
