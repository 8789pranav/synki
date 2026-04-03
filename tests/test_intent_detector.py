"""
Tests for intent detection.
"""

import pytest

from synki.models import IntentType
from synki.orchestrator.intent_detector import IntentDetector


class TestIntentDetector:
    """Test intent detection functionality."""
    
    @pytest.fixture
    def detector(self):
        return IntentDetector()
    
    def test_detect_greeting_english(self, detector):
        """Test detecting greeting in English."""
        intent, confidence = detector.detect("hi there!")
        assert intent == IntentType.GREETING
        assert confidence > 0.3
    
    def test_detect_greeting_hindi(self, detector):
        """Test detecting greeting in Hindi."""
        intent, confidence = detector.detect("namaste, kaise ho?")
        assert intent == IntentType.GREETING
        assert confidence > 0.3
    
    def test_detect_farewell(self, detector):
        """Test detecting farewell."""
        intent, confidence = detector.detect("bye, good night!")
        assert intent == IntentType.FAREWELL
        assert confidence > 0.3
    
    def test_detect_question(self, detector):
        """Test detecting questions."""
        intent, confidence = detector.detect("what are you doing?")
        assert intent == IntentType.QUESTION
        
        intent, confidence = detector.detect("kya chal raha hai?")
        assert intent == IntentType.QUESTION
    
    def test_detect_emotional_support(self, detector):
        """Test detecting emotional support need."""
        intent, confidence = detector.detect("I feel so sad and alone today")
        assert intent == IntentType.EMOTIONAL_SUPPORT
        assert confidence > 0.3
    
    def test_detect_statement(self, detector):
        """Test detecting statements."""
        intent, confidence = detector.detect("I had a meeting today")
        assert intent == IntentType.STATEMENT
    
    def test_is_question(self, detector):
        """Test question check helper."""
        assert detector.is_question("what time is it?")
        assert not detector.is_question("I am fine")
    
    def test_needs_emotional_response(self, detector):
        """Test emotional response check."""
        assert detector.needs_emotional_response("I feel so stressed")
        assert not detector.needs_emotional_response("hello!")
    
    def test_is_conversation_ender(self, detector):
        """Test conversation end detection."""
        assert detector.is_conversation_ender("bye bye, good night!")
        assert not detector.is_conversation_ender("hello!")
    
    def test_empty_text(self, detector):
        """Test empty text returns casual chat."""
        intent, confidence = detector.detect("")
        assert intent == IntentType.CASUAL_CHAT
