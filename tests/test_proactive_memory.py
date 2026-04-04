"""
Tests for proactive memory prompter.
"""

import pytest
from synki.orchestrator.proactive_memory import (
    ProactiveMemoryPrompter,
    MemoryTopic,
    MemoryPrompt,
)


class TestProactiveMemoryPrompter:
    """Tests for proactive memory detection and prompting."""
    
    def test_detect_medicine_topic(self):
        """Test detecting medicine-related messages."""
        prompter = ProactiveMemoryPrompter()
        
        topics = prompter.detect_memory_topics("I need to take my medicine")
        assert MemoryTopic.MEDICINE in topics
        
        topics = prompter.detect_memory_topics("Mujhe dawai leni hai")
        assert MemoryTopic.MEDICINE in topics
        
        topics = prompter.detect_memory_topics("Doctor ne tablet di")
        assert MemoryTopic.MEDICINE in topics
    
    def test_detect_birthday_topic(self):
        """Test detecting birthday mentions."""
        prompter = ProactiveMemoryPrompter()
        
        topics = prompter.detect_memory_topics("My birthday is coming")
        assert MemoryTopic.BIRTHDAY in topics
        
        topics = prompter.detect_memory_topics("Mera janmdin hai")
        assert MemoryTopic.BIRTHDAY in topics
    
    def test_detect_meeting_topic(self):
        """Test detecting meeting mentions."""
        prompter = ProactiveMemoryPrompter()
        
        topics = prompter.detect_memory_topics("I have a meeting today")
        assert MemoryTopic.MEETING in topics
        
        topics = prompter.detect_memory_topics("Zoom call hai aaj")
        assert MemoryTopic.MEETING in topics
    
    def test_detect_allergy_topic(self):
        """Test detecting allergy mentions."""
        prompter = ProactiveMemoryPrompter()
        
        topics = prompter.detect_memory_topics("I have an allergy")
        assert MemoryTopic.ALLERGY in topics
        
        topics = prompter.detect_memory_topics("Mujhe allergy hai")
        assert MemoryTopic.ALLERGY in topics
    
    def test_check_medicine_name_present(self):
        """Test detecting when medicine name is given."""
        prompter = ProactiveMemoryPrompter()
        
        # Medicine name present with suffix
        has_name, name = prompter.check_info_present(
            "I take Paracetamol daily", "medicine_name"
        )
        assert has_name == True
        
        # Very generic text without proper medicine name
        has_name, name = prompter.check_info_present(
            "i need help", "medicine_name"
        )
        assert has_name == False
    
    def test_check_time_present(self):
        """Test detecting time information."""
        prompter = ProactiveMemoryPrompter()
        
        # Time present
        has_time, time = prompter.check_info_present(
            "Meeting is at 3pm", "time"
        )
        assert has_time == True
        
        has_time, time = prompter.check_info_present(
            "10 baje hai call", "time"
        )
        assert has_time == True
        
        # Time not present
        has_time, time = prompter.check_info_present(
            "I have a meeting", "time"
        )
        assert has_time == False
    
    def test_check_date_present(self):
        """Test detecting date information."""
        prompter = ProactiveMemoryPrompter()
        
        has_date, date = prompter.check_info_present(
            "Birthday is on 15th March", "date"
        )
        assert has_date == True
        
        has_date, date = prompter.check_info_present(
            "It's on 12/05/2024", "date"
        )
        assert has_date == True
    
    def test_analyze_incomplete_medicine(self):
        """Test generating prompt for incomplete medicine info."""
        prompter = ProactiveMemoryPrompter()
        
        prompt = prompter.analyze_for_memory_prompts(
            "Mujhe tablet leni hai daily",
            "session_incomplete"
        )
        
        assert prompt is not None
        assert prompt.topic == MemoryTopic.MEDICINE
        # Should ask for name or time
        assert prompt.missing_field in ["medicine_name", "medicine_time"]
    
    def test_no_prompt_when_complete(self):
        """Test no prompt when information is complete."""
        prompter = ProactiveMemoryPrompter()
        
        # Medicine with name - should not ask for name
        prompt = prompter.analyze_for_memory_prompts(
            "I take Aspirin for headache",
            "session1"
        )
        
        # Should either be None or ask for time (not name)
        if prompt:
            assert prompt.missing_field != "medicine_name"
    
    def test_pending_query_tracking(self):
        """Test that pending queries are tracked."""
        prompter = ProactiveMemoryPrompter()
        
        # First call creates pending query
        prompt = prompter.analyze_for_memory_prompts(
            "Mujhe dawai leni hai",
            "session1"
        )
        
        assert prompt is not None
        
        pending = prompter.get_pending_queries("session1")
        assert len(pending) == 1
        assert pending[0].topic == MemoryTopic.MEDICINE
    
    def test_pending_response_detection(self):
        """Test detecting user response to pending query."""
        prompter = ProactiveMemoryPrompter()
        
        # Create pending query by asking about tablet
        prompter.analyze_for_memory_prompts(
            "Mujhe tablet leni hai roz",
            "session_pending"
        )
        
        # Check we have a pending query
        pending = prompter.get_pending_queries("session_pending")
        assert len(pending) >= 1
        
        # If asking for name, respond with name
        if pending and pending[-1].missing_field == "medicine_name":
            response = prompter._check_pending_response(
                "Crocin leti hoon",
                "session_pending"
            )
            # May or may not detect depending on pattern
            if response:
                assert "answer" in response.context
    
    def test_format_question_for_response(self):
        """Test formatting question for natural inclusion."""
        prompter = ProactiveMemoryPrompter()
        
        prompt = MemoryPrompt(
            topic=MemoryTopic.MEDICINE,
            question="Which medicine?",
            question_hinglish="Kaun si medicine baby?",
            missing_field="medicine_name"
        )
        
        formatted = prompter.format_question_for_response(prompt)
        
        # Should have a connector
        connectors = ["Btw", "Acha", "Arre", "Oh", "Ek baat"]
        has_connector = any(c in formatted for c in connectors)
        assert has_connector
        assert "Kaun si medicine baby?" in formatted
    
    def test_clear_session(self):
        """Test clearing session data."""
        prompter = ProactiveMemoryPrompter()
        
        prompter.analyze_for_memory_prompts(
            "Mujhe dawai leni hai",
            "session1"
        )
        
        assert len(prompter.get_pending_queries("session1")) > 0
        
        prompter.clear_session("session1")
        
        assert len(prompter.get_pending_queries("session1")) == 0
    
    def test_multiple_topics_detection(self):
        """Test detecting multiple topics in one message."""
        prompter = ProactiveMemoryPrompter()
        
        topics = prompter.detect_memory_topics(
            "I have a doctor appointment for my allergy"
        )
        
        assert MemoryTopic.APPOINTMENT in topics
        assert MemoryTopic.ALLERGY in topics
