"""
Context Manager

Manages conversation context including recent history,
topic tracking, and context packaging for LLM calls.
"""

import structlog

from ..models import (
    ContextPacket,
    EmotionState,
    IntentType,
    SessionState,
)

logger = structlog.get_logger(__name__)


class ContextManager:
    """Manages conversation context for the orchestrator."""
    
    def __init__(self, max_history: int = 5):
        """
        Initialize context manager.
        
        Args:
            max_history: Maximum messages to keep in history
        """
        self.max_history = max_history
    
    def build_context_packet(
        self,
        session: SessionState,
        current_text: str,
        emotion: EmotionState,
        intent: IntentType,
    ) -> ContextPacket:
        """
        Build a context packet for the current turn.
        
        Args:
            session: Current session state
            current_text: Current user utterance
            emotion: Detected emotion
            intent: Detected intent
            
        Returns:
            ContextPacket with all relevant context
        """
        # Get recent messages from session
        recent_user = session.context.recent_user_messages.copy()
        recent_assistant = session.context.recent_assistant_messages.copy()
        
        # Add current message
        if current_text and current_text not in recent_user:
            recent_user.append(current_text)
        
        # Detect topic from recent messages
        topic = self._detect_topic(recent_user + recent_assistant)
        
        return ContextPacket(
            recent_user_messages=recent_user[-self.max_history:],
            recent_assistant_messages=recent_assistant[-self.max_history:],
            current_topic=topic,
            last_mood=emotion,
            last_intent=intent,
            turn_count=session.turn_count,
            session_duration_ms=session.context.session_duration_ms,
        )
    
    def get_compact_history(
        self,
        context: ContextPacket,
        max_items: int = 3,
    ) -> list[str]:
        """
        Get compact history summary for LLM prompt.
        
        Args:
            context: Current context packet
            max_items: Maximum items to include
            
        Returns:
            List of compact history summaries
        """
        history = []
        
        # Interleave user and assistant messages
        user_msgs = context.recent_user_messages[-max_items:]
        asst_msgs = context.recent_assistant_messages[-max_items:]
        
        for i in range(max(len(user_msgs), len(asst_msgs))):
            if i < len(user_msgs):
                history.append(f"User: {user_msgs[i][:100]}")
            if i < len(asst_msgs):
                history.append(f"You: {asst_msgs[i][:100]}")
        
        return history[-max_items * 2:]
    
    def _detect_topic(self, messages: list[str]) -> str:
        """
        Detect current conversation topic from messages.
        
        Args:
            messages: Recent messages
            
        Returns:
            Detected topic string
        """
        if not messages:
            return "general"
        
        # Join recent messages for analysis
        text = " ".join(messages).lower()
        
        # Topic keywords mapping
        topic_keywords = {
            "work_stress": ["kaam", "office", "meeting", "boss", "tired", "thak", "stress"],
            "food": ["khana", "food", "dinner", "lunch", "breakfast", "hungry", "bhook"],
            "sleep": ["neend", "sleep", "sone", "jagaa", "tired", "thak"],
            "entertainment": ["movie", "film", "song", "gana", "music", "show", "game"],
            "relationships": ["friend", "dost", "family", "ghar", "mummy", "papa"],
            "health": ["health", "sick", "bimar", "doctor", "medicine", "tabiyat"],
            "weather": ["weather", "mausam", "garmi", "sardi", "baarish"],
            "plans": ["plan", "kal", "tomorrow", "weekend", "holiday"],
        }
        
        # Find matching topic
        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                return topic
        
        return "general"
    
    def should_change_topic(self, context: ContextPacket) -> bool:
        """
        Determine if conversation needs a topic change.
        
        Args:
            context: Current context packet
            
        Returns:
            True if topic change is recommended
        """
        # Suggest topic change if:
        # 1. Same topic for too many turns
        # 2. User seems bored (low engagement in messages)
        # 3. Repeated patterns detected
        
        if context.turn_count > 10 and context.current_topic != "general":
            return True
        
        # Check for repetitive user messages
        if len(context.recent_user_messages) >= 3:
            messages = context.recent_user_messages[-3:]
            avg_length = sum(len(m) for m in messages) / len(messages)
            if avg_length < 10:  # Very short responses might indicate disengagement
                return True
        
        return False
    
    def get_context_summary(self, context: ContextPacket) -> str:
        """
        Get a natural language summary of context for prompts.
        
        Args:
            context: Current context packet
            
        Returns:
            Context summary string
        """
        parts = []
        
        if context.current_topic and context.current_topic != "general":
            topic_map = {
                "work_stress": "talking about work and stress",
                "food": "discussing food",
                "sleep": "talking about sleep",
                "entertainment": "chatting about entertainment",
                "relationships": "discussing relationships",
                "health": "talking about health",
                "weather": "discussing weather",
                "plans": "making plans",
            }
            parts.append(f"Currently {topic_map.get(context.current_topic, 'chatting')}")
        
        if context.last_mood != EmotionState.NEUTRAL:
            mood_map = {
                EmotionState.HAPPY: "user seems happy",
                EmotionState.SAD: "user seems sad",
                EmotionState.TIRED: "user seems tired",
                EmotionState.STRESSED: "user is stressed",
                EmotionState.EXCITED: "user is excited",
                EmotionState.BORED: "user might be bored",
                EmotionState.ANGRY: "user seems upset",
                EmotionState.ANXIOUS: "user seems anxious",
            }
            parts.append(mood_map.get(context.last_mood, ""))
        
        if context.turn_count > 0:
            parts.append(f"conversation turn {context.turn_count}")
        
        return ". ".join(filter(None, parts))
