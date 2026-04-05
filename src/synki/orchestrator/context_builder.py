"""
Context Builder - Smart, Human-like Context for AI Prompts

KEY FEATURES:
1. Uses ALL 3 conversation summaries for context
2. SMART anti-repetition: tracks QUESTIONS asked, not topics
3. Time + Mood + History based suggestions (not just food!)
4. Tracks dislikes too (not just favorites)
5. Natural conversation FLOW - tracks last few exchanges, not just questions
6. Varied suggestions based on context (activities, not just food!)

NO extra storage - just smart formatting of existing data!
"""

import json
import random
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PromptContext:
    """
    Ready-to-use context for AI prompts.
    Computed at runtime, not stored.
    """
    # User basics
    user_name: str = "Baby"
    current_mood: str = "neutral"
    stress_level: str = "low"
    
    # Time context
    time_of_day: str = "day"  # morning, afternoon, evening, night
    time_based_hint: str = ""
    
    # Recent chat messages from THIS session (for context continuity)
    recent_chat_messages: list[dict] = field(default_factory=list)
    
    # Recent summaries from PREVIOUS sessions (ALL 3, with dates)
    recent_summaries: list[dict] = field(default_factory=list)
    
    # SMART Anti-repetition (questions, not topics!)
    questions_already_asked: list[str] = field(default_factory=list)
    facts_already_mentioned: list[str] = field(default_factory=list)
    last_question_category: str = ""  # To prevent consecutive similar questions
    
    # Conversation FLOW tracking (last few topics discussed)
    conversation_flow: list[str] = field(default_factory=list)  # Last 5 topic categories
    
    # User preferences
    likes: dict = field(default_factory=dict)
    dislikes: dict = field(default_factory=dict)
    
    # Behavior hints
    behavior_hint: str = ""
    suggested_follow_ups: list[str] = field(default_factory=list)
    
    # Smart contextual suggestion (based on mood + time + history)
    contextual_suggestion: str = ""


class ContextBuilder:
    """
    Builds smart, human-like prompt context.
    
    SMART ANTI-REPETITION:
    - Track QUESTIONS asked (not topics to avoid)
    - Prevent consecutive similar questions
    - Allow natural conversation about any topic
    - Just don't ask the SAME question again
    
    CONVERSATION FLOW:
    - Track last 5 topic categories discussed
    - Maintain natural conversation flow
    - Don't jump randomly - follow the vibe
    
    Usage:
        builder = ContextBuilder(supabase)
        context = await builder.build_context(user_id, user_message)
        prompt_text = builder.format_for_prompt(context)
    """
    
    MAX_SUMMARIES_IN_PROMPT = 3
    
    # Question categories for preventing consecutive similar questions
    QUESTION_CATEGORIES = {
        "food": ["khana", "food", "eat", "lunch", "dinner", "breakfast", "snack", "chai", "coffee"],
        "work": ["work", "office", "job", "kaam", "boss", "meeting", "project"],
        "health": ["health", "tired", "sick", "doctor", "sleep", "gym", "exercise"],
        "travel": ["trip", "travel", "vacation", "plan", "visit", "ghumne"],
        "family": ["family", "mom", "dad", "brother", "sister", "parents", "ghar"],
        "mood": ["feel", "mood", "happy", "sad", "stress", "bore", "excited"],
        "entertainment": ["movie", "song", "music", "game", "series", "show", "watch"],
        "relationship": ["miss", "love", "pyaar", "date", "together"],
    }
    
    # Time-based suggestions (VARIED - not just food!)
    TIME_SUGGESTIONS = {
        "morning": {
            "food": ["Nashta ho gaya? Poha ya paratha?", "Chai pee li?"],
            "activity": ["Morning walk ki?", "Aaj ka plan kya hai?"],
            "mood": ["Neend poori hui?", "Fresh feel ho raha hai?"],
            "work": ["Office time ho gaya?", "Aaj kya karna hai?"],
        },
        "afternoon": {
            "food": ["Lunch ho gaya baby?", "Kuch khaya?"],
            "activity": ["Break le liya?", "Busy day hai?"],
            "mood": ["Tired feel ho raha?", "Kaise chal raha din?"],
            "work": ["Meetings zyada thi?", "Kaam kaisa chal raha?"],
        },
        "evening": {
            "food": ["Chai time! Kuch khaya?", "Snacks khaye?"],
            "activity": ["Aaj kya plan hai evening ka?", "Ghumne chalein?"],
            "mood": ["Relax feel ho raha?", "Thak gaya/gayi?"],
            "entertainment": ["Koi movie dekhein?", "Music sun rahe ho?"],
        },
        "night": {
            "food": ["Dinner ho gaya?", "Kuch light khaya?"],
            "activity": ["Kal ka kya plan?", "Sone ka time ho gaya"],
            "mood": ["Tired lag raha?", "Aaj kaisa raha din?"],
            "entertainment": ["Kuch dekh rahe ho?", "Netflix chal raha?"],
        },
        "late_night": {
            "mood": ["So jao na baby", "Itni raat ko jaag rahe ho?"],
            "activity": ["Neend nahi aa rahi?", "Kya soch rahe ho?"],
            "relationship": ["Miss kar rahe the mujhe?", "Akele feel ho raha?"],
        },
    }
    
    def __init__(self, supabase_client: Any = None):
        self._supabase = supabase_client
        
        # Session-level tracking
        self._session_questions_asked: dict[str, list[str]] = {}  # user_id -> questions asked
        self._session_facts_mentioned: dict[str, set] = {}  # user_id -> facts mentioned
        self._session_last_question_category: dict[str, str] = {}  # user_id -> last category
        self._session_conversation_flow: dict[str, list[str]] = {}  # user_id -> last 5 topic categories
        
        logger.info("ContextBuilder initialized (smart conversation flow)")
    
    def get_time_context(self) -> tuple[str, str]:
        """Get current time period (just the period, not fixed suggestions)"""
        hour = datetime.now().hour
        
        if 5 <= hour < 11:
            return "morning", "🌅 Morning"
        elif 11 <= hour < 15:
            return "afternoon", "☀️ Afternoon"
        elif 15 <= hour < 19:
            return "evening", "🌆 Evening"
        elif 19 <= hour < 22:
            return "night", "🌙 Night"
        else:
            return "late_night", "🌃 Late night"
    
    def _get_smart_suggestion(
        self,
        time_of_day: str,
        mood: str,
        stress: str,
        conversation_flow: list[str],
        questions_asked: list[str],
    ) -> str:
        """
        Generate a SMART suggestion based on:
        - Time of day
        - User's mood & stress level
        - Recent conversation flow (avoid repetition)
        - Questions already asked
        
        Returns a contextual suggestion that's NOT repetitive.
        """
        suggestions = self.TIME_SUGGESTIONS.get(time_of_day, {})
        if not suggestions:
            return ""
        
        # Get categories we should AVOID (recently discussed)
        avoid_categories = set(conversation_flow[-3:]) if conversation_flow else set()
        
        # Priority based on mood
        priority_categories = []
        if mood in ["sad", "down", "upset"]:
            priority_categories = ["mood", "relationship", "entertainment"]
        elif mood in ["stressed", "anxious", "tense"]:
            priority_categories = ["mood", "activity", "entertainment"]
        elif mood in ["tired", "exhausted"]:
            priority_categories = ["mood", "food", "activity"]
        elif mood in ["happy", "excited"]:
            priority_categories = ["activity", "entertainment", "food"]
        elif stress == "high":
            priority_categories = ["mood", "activity", "entertainment"]
        else:
            # Random mix for neutral mood
            priority_categories = list(suggestions.keys())
            random.shuffle(priority_categories)
        
        # Find a category that's not recently discussed
        selected_category = None
        for cat in priority_categories:
            if cat in suggestions and cat not in avoid_categories:
                selected_category = cat
                break
        
        # If all priority categories were discussed, pick any available
        if not selected_category:
            available = [c for c in suggestions.keys() if c not in avoid_categories]
            if available:
                selected_category = random.choice(available)
            else:
                # Last resort - pick any
                selected_category = random.choice(list(suggestions.keys()))
        
        # Get suggestion from selected category
        category_suggestions = suggestions.get(selected_category, [])
        if not category_suggestions:
            return ""
        
        # Filter out questions already asked
        available_suggestions = [
            s for s in category_suggestions
            if not any(q in s.lower() for q in [qa.lower() for qa in questions_asked[-5:]])
        ]
        
        if available_suggestions:
            return f"💡 Maybe ask: {random.choice(available_suggestions)}"
        elif category_suggestions:
            return f"💡 Maybe ask: {random.choice(category_suggestions)}"
        return ""
    
    def track_conversation_topic(self, user_id: str, message: str):
        """Track what topic was just discussed (for flow)"""
        category = self._get_question_category(message)
        if category:
            if user_id not in self._session_conversation_flow:
                self._session_conversation_flow[user_id] = []
            self._session_conversation_flow[user_id].append(category)
            # Keep only last 5
            self._session_conversation_flow[user_id] = self._session_conversation_flow[user_id][-5:]
    
    async def build_context(
        self,
        user_id: str,
        user_message: str = "",
        recent_messages: list[dict] | None = None,
    ) -> PromptContext:
        """
        Build smart context from existing data.
        
        Args:
            user_id: User's unique ID
            user_message: Current user message
            recent_messages: List of recent chat messages from current session
                            [{"role": "user"|"assistant", "content": "..."}]
        """
        context = PromptContext()
        
        # Store recent chat messages (last N messages from this session)
        if recent_messages:
            context.recent_chat_messages = recent_messages[-10:]  # Last 10 messages
        
        # 1. Time context
        context.time_of_day, context.time_based_hint = self.get_time_context()
        
        # 2. Load memories (likes AND dislikes)
        memories = await self._get_memories(user_id)
        if memories:
            context.user_name = memories.get("name", "Baby")
            context.likes, context.dislikes = self._extract_preferences(memories)
        
        # 3. Load short-term profile
        short_term = await self._get_short_term_profile(user_id)
        if short_term:
            context.current_mood = short_term.get("dominant_mood", "neutral")
            context.stress_level = short_term.get("stress_level", "low")
            context.behavior_hint = self._get_behavior_hint(
                context.current_mood,
                context.stress_level
            )
        
        # 4. Load ALL 3 recent summaries
        summaries = await self._get_recent_summaries(user_id)
        context.recent_summaries = [
            {
                "date": s.get("conversation_date", "unknown"),
                "summary": s.get("summary", ""),
                "topics": s.get("topics", []),
                "emotions": s.get("emotions_detected", []),
            }
            for s in summaries
        ]
        
        # 5. SMART anti-repetition: track QUESTIONS, not topics
        context.questions_already_asked = self._session_questions_asked.get(user_id, [])
        context.facts_already_mentioned = list(self._session_facts_mentioned.get(user_id, set()))
        context.last_question_category = self._session_last_question_category.get(user_id, "")
        
        # 6. Conversation FLOW tracking
        context.conversation_flow = self._session_conversation_flow.get(user_id, [])
        
        # 7. SMART contextual suggestion (based on mood + time + flow)
        context.contextual_suggestion = self._get_smart_suggestion(
            time_of_day=context.time_of_day,
            mood=context.current_mood,
            stress=context.stress_level,
            conversation_flow=context.conversation_flow,
            questions_asked=context.questions_already_asked,
        )
        
        # 8. Generate suggested follow-ups (avoiding duplicates)
        context.suggested_follow_ups = self._generate_smart_followups(
            context, user_message
        )
        
        return context
    
    def track_question_asked(self, user_id: str, question: str):
        """Track a question that was asked (for anti-repetition)"""
        if user_id not in self._session_questions_asked:
            self._session_questions_asked[user_id] = []
        self._session_questions_asked[user_id].append(question.lower())
        
        # Also track the category to prevent consecutive similar questions
        category = self._get_question_category(question)
        if category:
            self._session_last_question_category[user_id] = category
            # Also add to conversation flow
            self.track_conversation_topic(user_id, question)
    
    def track_fact_mentioned(self, user_id: str, fact: str):
        """Track that a fact was mentioned (e.g., 'favorite movie')"""
        if user_id not in self._session_facts_mentioned:
            self._session_facts_mentioned[user_id] = set()
        self._session_facts_mentioned[user_id].add(fact.lower())
    
    def reset_session_tracking(self, user_id: str):
        """Reset session tracking (call at session end)"""
        self._session_questions_asked.pop(user_id, None)
        self._session_facts_mentioned.pop(user_id, None)
        self._session_last_question_category.pop(user_id, None)
    
    def _get_question_category(self, question: str) -> str:
        """Determine the category of a question"""
        question_lower = question.lower()
        for category, keywords in self.QUESTION_CATEGORIES.items():
            if any(kw in question_lower for kw in keywords):
                return category
        return ""
    
    def is_similar_to_last_question(self, user_id: str, new_question: str) -> bool:
        """Check if new question is in same category as last question"""
        new_category = self._get_question_category(new_question)
        last_category = self._session_last_question_category.get(user_id, "")
        
        if not new_category or not last_category:
            return False
        
        return new_category == last_category
    
    def format_for_prompt(self, context: PromptContext) -> str:
        """
        Format context for LLM prompt injection.
        
        SMART approach: 
        - Track conversation FLOW (not just individual questions)
        - Suggest based on mood + time + history
        - Maintain natural conversation continuity
        """
        parts = []
        
        # =====================================================================
        # USER INFO + MOOD
        # =====================================================================
        parts.append(f"## About {context.user_name}")
        parts.append(f"Mood: {context.current_mood} | Stress: {context.stress_level} | {context.time_based_hint}")
        
        # =====================================================================
        # RECENT CHAT (current session - for continuity)
        # =====================================================================
        if context.recent_chat_messages:
            parts.append("\n## Recent Chat (CONTINUE this conversation naturally!):")
            for msg in context.recent_chat_messages[-6:]:  # Last 6 messages for context
                role = "User" if msg.get("role") == "user" else "You"
                content = msg.get("content", "")[:150]  # Truncate for prompt space
                if len(msg.get("content", "")) > 150:
                    content += "..."
                parts.append(f"   {role}: {content}")
        
        # =====================================================================
        # CONVERSATION FLOW (what topics we've covered)
        # =====================================================================
        if context.conversation_flow:
            flow_str = " → ".join(context.conversation_flow[-5:])
            parts.append(f"\n📊 Conversation flow: {flow_str}")
            parts.append(f"   → Next topic should be DIFFERENT from: {context.conversation_flow[-1] if context.conversation_flow else 'none'}")
        
        # =====================================================================
        # BEHAVIOR GUIDANCE
        # =====================================================================
        if context.behavior_hint:
            parts.append(f"\n🎯 Behavior: {context.behavior_hint}")
        
        # =====================================================================
        # SMART CONTEXTUAL SUGGESTION (mood + time + history based)
        # =====================================================================
        if context.contextual_suggestion:
            parts.append(f"\n{context.contextual_suggestion}")
        
        # =====================================================================
        # PREVIOUS SESSIONS (summaries for long-term context)
        # =====================================================================
        if context.recent_summaries:
            parts.append("\n## Previous Conversations (for reference):")
            for i, s in enumerate(context.recent_summaries, 1):
                date = s["date"]
                summary = s["summary"]
                emotions = ", ".join(s.get("emotions", [])) or "neutral"
                parts.append(f"   [{date}] {summary[:100]}...")
            
            parts.append("   ✅ You CAN follow up on these naturally")
        
        # =====================================================================
        # PREFERENCES (use when relevant)
        # =====================================================================
        if context.likes or context.dislikes:
            parts.append("\n## Preferences:")
            if context.likes:
                likes_list = [f"{k}={v}" for k, v in list(context.likes.items())[:5]]
                parts.append(f"   👍 {', '.join(likes_list)}")
            if context.dislikes:
                dislikes_list = [f"{k}={v}" for k, v in list(context.dislikes.items())[:5]]
                parts.append(f"   👎 AVOID: {', '.join(dislikes_list)}")
        
        # =====================================================================
        # ANTI-REPETITION (exact questions asked)
        # =====================================================================
        if context.questions_already_asked:
            parts.append(f"\n🚫 Don't repeat these questions:")
            for q in context.questions_already_asked[-5:]:
                parts.append(f"   ❌ \"{q}\"")
        
        # =====================================================================
        # NATURAL CONVERSATION RULES
        # =====================================================================
        parts.append("""
## 🧠 BE NATURAL:
1. CONTINUE the current conversation flow - don't jump randomly
2. If user is talking about work, stay on work for 2-3 exchanges before switching
3. Don't ask same category question consecutively (food→food BAD, food→mood GOOD)
4. ONE question per response max
5. Be a caring girlfriend who LISTENS, not interrogates!""")
        
        return "\n".join(parts)
    
    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================
    
    async def _get_memories(self, user_id: str) -> dict:
        """Get memories from database"""
        if not self._supabase:
            return {}
        
        try:
            result = self._supabase.table("memories")\
                .select("name, facts, preferences")\
                .eq("user_id", user_id)\
                .execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return {}
    
    async def _get_short_term_profile(self, user_id: str) -> dict:
        """Get short-term profile from database"""
        if not self._supabase:
            return {}
        
        try:
            result = self._supabase.table("user_profiles_short_term")\
                .select("profile_data")\
                .eq("user_id", user_id)\
                .execute()
            return result.data[0].get("profile_data", {}) if result.data else {}
        except Exception as e:
            logger.error(f"Failed to get short-term profile: {e}")
            return {}
    
    async def _get_recent_summaries(self, user_id: str) -> list[dict]:
        """Get ALL 3 recent conversation summaries"""
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.table("conversation_summaries")\
                .select("summary, topics, emotions_detected, conversation_date")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(self.MAX_SUMMARIES_IN_PROMPT)\
                .execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get summaries: {e}")
            return []
    
    def _extract_preferences(self, memories: dict) -> tuple[dict, dict]:
        """Extract likes AND dislikes from memories"""
        likes = {}
        dislikes = {}
        
        facts = memories.get("facts", [])
        for fact in facts:
            key = fact.get("key", "").lower()
            value = fact.get("value", "")
            
            if not key or not value:
                continue
            
            # Categorize as like or dislike
            if "favorite" in key or "like" in key or "love" in key:
                category = key.replace("favorite_", "").replace("likes_", "").replace("loves_", "")
                likes[category] = value
            elif "dislike" in key or "hate" in key or "dont_like" in key or "avoid" in key or "not_like" in key:
                category = key.replace("dislikes_", "").replace("hates_", "").replace("dont_like_", "").replace("avoids_", "").replace("not_like_", "")
                dislikes[category] = value
        
        # Also check preferences field
        preferences = memories.get("preferences", {})
        if isinstance(preferences, dict):
            likes.update(preferences.get("likes", {}))
            dislikes.update(preferences.get("dislikes", {}))
        
        return likes, dislikes
    
    def _get_behavior_hint(self, mood: str, stress: str) -> str:
        """Get behavior hint based on user's current state"""
        hints = {
            "happy": "Be playful, share excitement, match their energy! 🎉",
            "sad": "Be gentle, listen more, offer comfort without forcing positivity 💙",
            "stressed": "Be calming, don't add pressure, just be supportive 🤗",
            "excited": "Share their excitement, ask what happened! ✨",
            "tired": "Keep responses SHORT, be caring, suggest rest 😴",
            "anxious": "Be reassuring and calm, no heavy topics 🌸",
            "angry": "Validate feelings, let them vent, don't argue 💪",
            "neutral": "Be warm and engaging, start interesting conversation 💕",
        }
        
        hint = hints.get(mood, hints["neutral"])
        
        if stress == "high":
            hint += " ⚠️ HIGH STRESS - be extra gentle!"
        
        return hint
    
    def _extract_topics_from_summaries(self, summaries: list[dict]) -> list[str]:
        """Extract ALL topics from ALL summaries (for anti-repetition)"""
        topics = set()
        
        for s in summaries:
            # Explicit topics
            summary_topics = s.get("topics", [])
            topics.update(t.lower() for t in summary_topics)
            
            # Keywords from summary text
            summary_text = s.get("summary", "").lower()
            keywords = [
                "trip", "movie", "food", "work", "boss", "family", "health",
                "maggi", "kerala", "brother", "sholay", "office", "stress",
                "travel", "vacation", "friend", "game", "music", "gym",
                "college", "exam", "interview", "meeting", "date", "party"
            ]
            for kw in keywords:
                if kw in summary_text:
                    topics.add(kw)
        
        return list(topics)
    
    def _generate_smart_followups(self, context: PromptContext, user_message: str) -> list[str]:
        """
        Generate smart, contextual follow-up questions.
        
        SMART: Avoids questions already asked, considers category diversity!
        """
        questions = []
        asked_questions = [q.lower() for q in context.questions_already_asked]
        last_category = context.last_question_category
        message_lower = user_message.lower() if user_message else ""
        
        def is_already_asked(q: str) -> bool:
            """Check if a similar question was already asked"""
            q_lower = q.lower()
            for asked in asked_questions:
                # Check for similar questions (not exact match)
                if q_lower in asked or asked in q_lower:
                    return True
                # Check key words overlap
                q_words = set(q_lower.split())
                asked_words = set(asked.split())
                overlap = len(q_words & asked_words)
                if overlap >= 3:  # 3+ words in common = similar
                    return True
            return False
        
        def get_category(q: str) -> str:
            """Get category of a question"""
            q_lower = q.lower()
            for cat, keywords in self.QUESTION_CATEGORIES.items():
                if any(kw in q_lower for kw in keywords):
                    return cat
            return ""
        
        # Time-based food suggestions (if food mentioned)
        if any(word in message_lower for word in ["food", "khana", "bhookh", "hungry", "eat", "khaate"]):
            food_questions = {
                "morning": "Breakfast mein kya loge? Paratha ya kuch light?",
                "afternoon": "Lunch ho gaya? Kya khaya?",
                "evening": "Chai ke saath kya loge? Snacks?",
                "night": "Dinner ka kya plan hai? Ghar pe ya bahar?",
                "late_night": "Itni raat ko kya khane ka mann hai?",
            }
            q = food_questions.get(context.time_of_day, food_questions["evening"])
            if not is_already_asked(q) and last_category != "food":
                questions.append(q)
        
        # Work-related (if work mentioned)
        if any(word in message_lower for word in ["work", "office", "kaam", "busy"]):
            q = "Aaj kya chal raha hai office mein?"
            if not is_already_asked(q) and last_category != "work":
                questions.append(q)
        
        # Tired (if tired mentioned)
        if any(word in message_lower for word in ["tired", "thak", "rest", "neend"]):
            q = "Bahut kaam ho gaya aaj? Rest karo thoda"
            if not is_already_asked(q) and last_category != "health":
                questions.append(q)
        
        # Follow-up from summaries (avoid consecutive same category)
        for summary in context.recent_summaries[:2]:
            topics = summary.get("topics", [])
            
            if "trip" in topics:
                q = "Woh trip ka plan hua jo bola tha?"
                if not is_already_asked(q) and last_category != "travel":
                    questions.append(q)
                    break
            
            if "stress" in topics or "work" in topics:
                q = "Ab kaam ka stress kam hua?"
                if not is_already_asked(q) and last_category != "work":
                    questions.append(q)
                    break
            
            if "family" in topics or "brother" in topics:
                q = "Ghar pe sab kaise hain?"
                if not is_already_asked(q) and last_category != "family":
                    questions.append(q)
                    break
        
        return questions[:3]  # Max 3 suggestions
        return questions[:3]  # Max 3 suggestions
