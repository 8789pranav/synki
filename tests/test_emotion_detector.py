"""
Tests for emotion detection.
"""

import pytest

from synki.models import EmotionState
from synki.orchestrator.emotion_detector import EmotionDetector


class TestEmotionDetector:
    """Test emotion detection functionality."""
    
    @pytest.fixture
    def detector(self):
        return EmotionDetector()
    
    def test_detect_tired_english(self, detector):
        """Test detecting tired emotion in English."""
        emotion, confidence = detector.detect("I'm so tired today")
        assert emotion == EmotionState.TIRED
        assert confidence > 0.2
    
    def test_detect_tired_hindi(self, detector):
        """Test detecting tired emotion in Hindi."""
        emotion, confidence = detector.detect("aaj bahut thak gaya")
        assert emotion == EmotionState.TIRED
        assert confidence > 0.2
    
    def test_detect_happy(self, detector):
        """Test detecting happy emotion."""
        emotion, confidence = detector.detect("I'm so happy today! Mast hai!")
        assert emotion == EmotionState.HAPPY
        assert confidence > 0.2
    
    def test_detect_sad(self, detector):
        """Test detecting sad emotion."""
        emotion, confidence = detector.detect("I feel so sad and alone")
        assert emotion == EmotionState.SAD
        assert confidence > 0.2
    
    def test_detect_stressed(self, detector):
        """Test detecting stressed emotion."""
        emotion, confidence = detector.detect("bohot stress ho raha hai deadline ke liye")
        assert emotion == EmotionState.STRESSED
        assert confidence > 0.2
    
    def test_detect_neutral(self, detector):
        """Test neutral emotion for ambiguous text."""
        emotion, confidence = detector.detect("okay")
        assert emotion == EmotionState.NEUTRAL
    
    def test_empty_text(self, detector):
        """Test empty text returns neutral."""
        emotion, confidence = detector.detect("")
        assert emotion == EmotionState.NEUTRAL
        assert confidence == 0.0
    
    def test_intensity_booster(self, detector):
        """Test that intensity boosters increase confidence."""
        emotion1, conf1 = detector.detect("tired")
        emotion2, conf2 = detector.detect("very tired")
        
        assert emotion1 == emotion2 == EmotionState.TIRED
        assert conf2 >= conf1
    
    def test_response_hint(self, detector):
        """Test getting response hints for emotions."""
        hint = detector.get_emotion_response_hint(EmotionState.SAD)
        assert "empathetic" in hint or "comfort" in hint
        
        hint = detector.get_emotion_response_hint(EmotionState.HAPPY)
        assert "playful" in hint or "energy" in hint
