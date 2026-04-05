"""
PERSONALIZED DYNAMIC CONTEXT BUILDER

Uses ALL available user data to create human-like, adaptive context:
1. Behavior patterns (what makes them happy/irritated)
2. Time-based energy levels
3. Topic effectiveness tracking
4. Mood triggers
5. Session flow intelligence
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class UserBehaviorProfile:
    """Deep user behavior analysis"""
    
    # Mood triggers
    happiness_triggers: list[str] = field(default_factory=list)  # What makes them happy
    stress_triggers: list[str] = field(default_factory=list)  # What stresses them
    
    # Energy by time
    energy_by_time: dict = field(default_factory=dict)  # morning: low, evening: high
    
    # Topic effectiveness (which topics lead to good conversations)
    topic_success_rate: dict = field(default_factory=dict)  # topic -> success_rate
    
    # Irritation patterns
    irritation_signals: list[str] = field(default_factory=list)  # Short responses patterns
    
    # Best conversation patterns
    best_conversation_endings: list[str] = field(default_factory=list)  # Topics that end well
    
    # Recent activities and interests
    recent_activities: list[dict] = field(default_factory=list)
    recent_locations: list[dict] = field(default_factory=list)
    
    # All favorites (not just food!)
    all_favorites: dict = field(default_factory=dict)  # category -> value


@dataclass
class SessionIntelligence:
    """Smart session tracking"""
    
    # Response mode for THIS turn
    response_mode: str = "REACT"  # REACT, FOLLOW_UP, NEW_TOPIC, COMFORT
    
    # Topics tracking
    topics_done: list[str] = field(default_factory=list)
    topics_available: list[str] = field(default_factory=list)
    
    # Favorites tracking
    favorites_suggested: list[str] = field(default_factory=list)
    favorites_available: list[str] = field(default_factory=list)
    
    # Mood trend in THIS session
    mood_trend: str = "stable"  # improving, declining, stable
    
    # Suggested next action
    suggested_action: str = ""
    
    # Time-appropriate suggestions
    time_suggestions: list[str] = field(default_factory=list)


class PersonalizedContextEngine:
    """
    Creates deeply personalized, human-like context.
    
    Uses:
    - Short-term profile (recent behavior)
    - Long-term profile (patterns)
    - Memories (facts, favorites)
    - Session tracking (what's done)
    - Time awareness
    - Random human-like elements
    """
    
    # All possible topics to track
    ALL_TOPICS = [
        "food", "work", "travel", "movie", "music", "family", 
        "health", "weekend", "hobby", "friend", "sleep", "day"
    ]
    
    # Response mode probabilities (makes it feel human)
    RESPONSE_MODES = {
        "REACT": 60,      # Just react, no question (60%)
        "FOLLOW_UP": 25,  # Follow up from previous talks (25%)
        "NEW_TOPIC": 10,  # Ask about new topic (10%)
        "RANDOM": 5,      # Random "aur batao" type (5%)
    }
    
    def __init__(self, supabase_client: Any = None):
        self._supabase = supabase_client
    
    async def build_personalized_context(
        self,
        user_id: str,
        current_mood: str,
        topics_done: list[str],
        favorites_suggested: list[str],
        recent_messages: list[dict],
    ) -> dict:
        """
        Build deeply personalized context for this turn.
        
        Returns dict with:
        - behavior: UserBehaviorProfile
        - session: SessionIntelligence
        - context_text: Formatted string for prompt
        """
        
        # 1. Load user behavior profile
        behavior = await self._load_behavior_profile(user_id)
        
        # 2. Build session intelligence
        session = self._build_session_intelligence(
            behavior=behavior,
            current_mood=current_mood,
            topics_done=topics_done,
            favorites_suggested=favorites_suggested,
            recent_messages=recent_messages,
        )
        
        # 3. Format context for prompt
        context_text = self._format_personalized_context(behavior, session, current_mood)
        
        return {
            "behavior": behavior,
            "session": session,
            "context_text": context_text,
        }
    
    async def _load_behavior_profile(self, user_id: str) -> UserBehaviorProfile:
        """Load and analyze user's behavior patterns"""
        profile = UserBehaviorProfile()
        
        if not self._supabase:
            return profile
        
        try:
            # Load short-term profile
            result = self._supabase.table("user_profiles_short_term")\
                .select("profile_data")\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                data = result.data[0].get("profile_data", {})
                
                # Extract happiness triggers
                profile.happiness_triggers = data.get("recent_happiness_triggers", [])
                
                # Extract stress triggers
                profile.stress_triggers = data.get("recent_stress_triggers", [])
                
                # Energy by time
                profile.energy_by_time = data.get("energy_by_time", {})
                
                # Recent activities
                profile.recent_activities = data.get("recent_activities", [])
                
                # Recent locations
                profile.recent_locations = data.get("recent_locations", [])
            
            # Load memories (favorites)
            mem_result = self._supabase.table("memories")\
                .select("facts, preferences")\
                .eq("user_id", user_id)\
                .execute()
            
            if mem_result.data:
                facts = mem_result.data[0].get("facts", [])
                for fact in facts:
                    key = fact.get("key", "")
                    value = fact.get("value", "")
                    if "favorite" in key.lower():
                        category = key.replace("favorite_", "")
                        profile.all_favorites[category] = value
            
            logger.info(f"Loaded behavior profile: {len(profile.happiness_triggers)} happiness triggers, {len(profile.all_favorites)} favorites")
            
        except Exception as e:
            logger.error(f"Failed to load behavior profile: {e}")
        
        return profile
    
    def _build_session_intelligence(
        self,
        behavior: UserBehaviorProfile,
        current_mood: str,
        topics_done: list[str],
        favorites_suggested: list[str],
        recent_messages: list[dict],
    ) -> SessionIntelligence:
        """Build smart session tracking"""
        
        session = SessionIntelligence()
        session.topics_done = topics_done
        session.favorites_suggested = favorites_suggested
        
        # Calculate available topics
        session.topics_available = [t for t in self.ALL_TOPICS if t not in topics_done]
        
        # Calculate available favorites
        session.favorites_available = [
            f"{k}: {v}" for k, v in behavior.all_favorites.items()
            if f"{k}:{v}" not in favorites_suggested
        ]
        
        # Determine response mode (with randomness!)
        session.response_mode = self._pick_response_mode(current_mood, topics_done)
        
        # Detect mood trend from recent messages
        session.mood_trend = self._detect_mood_trend(recent_messages)
        
        # Get time-appropriate suggestions
        session.time_suggestions = self._get_time_suggestions()
        
        # Build suggested action
        session.suggested_action = self._build_suggested_action(
            session.response_mode,
            current_mood,
            behavior,
            session,
        )
        
        return session
    
    def _pick_response_mode(self, mood: str, topics_done: list[str]) -> str:
        """Pick response mode with human-like randomness"""
        
        # Adjust probabilities based on mood
        if mood in ["sad", "stressed", "tired"]:
            # More comfort, less questions
            weights = {"REACT": 75, "FOLLOW_UP": 15, "NEW_TOPIC": 5, "RANDOM": 5}
        elif mood in ["happy", "excited"]:
            # Can ask more, share joy
            weights = {"REACT": 50, "FOLLOW_UP": 30, "NEW_TOPIC": 15, "RANDOM": 5}
        elif len(topics_done) >= 3:
            # Already discussed a lot, mostly react
            weights = {"REACT": 80, "FOLLOW_UP": 10, "NEW_TOPIC": 5, "RANDOM": 5}
        else:
            # Normal distribution
            weights = self.RESPONSE_MODES
        
        # Random pick
        choices = []
        for mode, weight in weights.items():
            choices.extend([mode] * weight)
        
        return random.choice(choices)
    
    def _detect_mood_trend(self, messages: list[dict]) -> str:
        """Detect if user's mood is improving or declining"""
        if len(messages) < 4:
            return "stable"
        
        # Check last few user messages
        user_msgs = [m for m in messages if m.get("role") == "user"][-4:]
        
        # Simple heuristic: message length trend
        lengths = [len(m.get("content", "")) for m in user_msgs]
        
        if len(lengths) >= 2:
            if lengths[-1] > lengths[0] * 1.5:
                return "improving"  # Getting more talkative
            elif lengths[-1] < lengths[0] * 0.5:
                return "declining"  # Getting shorter responses
        
        return "stable"
    
    def _get_time_suggestions(self) -> list[str]:
        """Get time-appropriate suggestions"""
        hour = datetime.now().hour
        
        if 5 <= hour < 9:
            return ["morning routine", "breakfast", "day plans", "sleep quality"]
        elif 9 <= hour < 12:
            return ["work start", "morning energy", "coffee/chai"]
        elif 12 <= hour < 14:
            return ["lunch", "midday break", "afternoon plans"]
        elif 14 <= hour < 18:
            return ["work progress", "afternoon energy", "evening plans"]
        elif 18 <= hour < 21:
            return ["dinner", "relaxing", "evening activities", "day recap"]
        else:  # Night
            return ["rest", "sleep soon", "tomorrow plans", "calm topics"]
    
    def _build_suggested_action(
        self,
        mode: str,
        mood: str,
        behavior: UserBehaviorProfile,
        session: SessionIntelligence,
    ) -> str:
        """Build specific action suggestion for this turn"""
        
        if mode == "REACT":
            reactions = [
                "Just acknowledge: 'haan sahi hai', 'acha', 'hmm'",
                "Show empathy: 'aww', 'samajh sakti hoon'",
                "Share feeling: 'mujhe bhi aisa lagta hai'",
            ]
            return random.choice(reactions)
        
        elif mode == "FOLLOW_UP":
            # Use happiness triggers or recent activities
            if behavior.happiness_triggers:
                trigger = random.choice(behavior.happiness_triggers)
                return f"Mention: '{trigger}' (makes them happy)"
            elif behavior.recent_activities:
                activity = random.choice(behavior.recent_activities)
                return f"Ask about: {activity.get('activity', 'recent activity')}"
            return "Follow up on something from previous talks"
        
        elif mode == "NEW_TOPIC":
            if session.topics_available:
                topic = random.choice(session.topics_available)
                return f"Ask about NEW topic: {topic}"
            return "Find something new to discuss"
        
        else:  # RANDOM
            randoms = [
                "Say: 'aur batao kuch maza aaya?'",
                "Say: 'kuch interesting hua aaj?'",
                "Just be curious naturally",
            ]
            return random.choice(randoms)
    
    def _format_personalized_context(
        self,
        behavior: UserBehaviorProfile,
        session: SessionIntelligence,
        current_mood: str,
    ) -> str:
        """Format the personalized context for prompt injection"""
        
        parts = []
        
        # Header with mode
        parts.append(f"🎲 Mode: {session.response_mode}")
        parts.append(f"📍 Action: {session.suggested_action}")
        
        # User behavior insights (only relevant ones)
        if current_mood in ["sad", "stressed", "bored"] and behavior.happiness_triggers:
            triggers = behavior.happiness_triggers[:3]
            parts.append(f"\n💡 Cheer up with: {', '.join(triggers)}")
        
        # Session tracking
        if session.topics_done:
            parts.append(f"\n✓ Done: {', '.join(session.topics_done)}")
        if session.topics_available:
            available = session.topics_available[:4]
            parts.append(f"○ Available: {', '.join(available)}")
        
        # Mood trend
        if session.mood_trend != "stable":
            if session.mood_trend == "improving":
                parts.append("📈 User opening up - keep going!")
            else:
                parts.append("📉 User getting quiet - be gentle")
        
        # Time context
        hour = datetime.now().hour
        if hour >= 22 or hour < 6:
            parts.append("\n🌙 Late night - soft, caring, suggest rest")
        
        # Favorites (only if mood needs it AND not already suggested)
        if current_mood in ["sad", "bored", "stressed"] and session.favorites_available:
            fav = random.choice(session.favorites_available)
            parts.append(f"\n🎁 Suggest (unused): {fav}")
        
        # Rules based on mode
        parts.append(f"\n⚡ This turn: {session.response_mode}")
        if session.response_mode == "REACT":
            parts.append("   → NO question, just respond warmly")
        elif session.response_mode == "NEW_TOPIC":
            parts.append(f"   → Ask about: {session.topics_available[0] if session.topics_available else 'something new'}")
        
        return "\n".join(parts)


# Export for use
__all__ = ["PersonalizedContextEngine", "UserBehaviorProfile", "SessionIntelligence"]
