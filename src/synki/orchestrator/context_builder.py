"""
Context Builder - Smart, Human-like Context for AI Prompts

KEY FEATURES:
1. Uses ALL 3 conversation summaries for context
2. SMART anti-repetition: tracks QUESTIONS asked, not topics
3. Time-aware suggestions (morning food vs night food)
4. Tracks dislikes too (not just favorites)
5. Natural human touch - doesn't block topics, just prevents same questions

NO extra storage - just smart formatting of existing data!
"""

import json
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
    
    # Recent summaries (ALL 3, with dates)
    recent_summaries: list[dict] = field(default_factory=list)
    
    # SMART Anti-repetition (questions, not topics!)
    questions_already_asked: list[str] = field(default_factory=list)
    facts_already_mentioned: list[str] = field(default_factory=list)
    last_question_category: str = ""  # To prevent consecutive similar questions
    
    # User preferences
    likes: dict = field(default_factory=dict)
    dislikes: dict = field(default_factory=dict)
    
    # Behavior hints
    behavior_hint: str = ""
    suggested_follow_ups: list[str] = field(default_factory=list)


class ContextBuilder:
    """
    Builds smart, human-like prompt context.
    
    SMART ANTI-REPETITION:
    - Track QUESTIONS asked (not topics to avoid)
    - Prevent consecutive similar questions
    - Allow natural conversation about any topic
    - Just don't ask the SAME question again
    
    Usage:
        builder = ContextBuilder(supabase)
        context = await builder.build_context(user_id, user_message)
        prompt_text = builder.format_for_prompt(context)
    """
    
    MAX_SUMMARIES_IN_PROMPT = 3
    
    # Question categories for preventing consecutive similar questions
    QUESTION_CATEGORIES = {
        "food": ["khana", "food", "eat", "lunch", "dinner", "breakfast", "snack"],
        "work": ["work", "office", "job", "kaam", "boss", "meeting"],
        "health": ["health", "tired", "sick", "doctor", "sleep"],
        "travel": ["trip", "travel", "vacation", "plan", "visit"],
        "family": ["family", "mom", "dad", "brother", "sister", "parents"],
        "mood": ["feel", "mood", "happy", "sad", "stress"],
    }
    
    def __init__(self, supabase_client: Any = None):
        self._supabase = supabase_client
        
        # Session-level tracking
        self._session_questions_asked: dict[str, list[str]] = {}  # user_id -> questions asked
        self._session_facts_mentioned: dict[str, set] = {}  # user_id -> facts mentioned
        self._session_last_question_category: dict[str, str] = {}  # user_id -> last category
        
        logger.info("ContextBuilder initialized (smart anti-repetition)")
    
    def get_time_context(self) -> tuple[str, str]:
        """Get current time period and food/activity hint"""
        hour = datetime.now().hour
        
        if 5 <= hour < 11:
            return "morning", "🌅 Morning - suggest: breakfast (paratha, poha, chai, omelette)"
        elif 11 <= hour < 15:
            return "afternoon", "☀️ Afternoon - suggest: lunch (dal chawal, roti sabzi, biryani)"
        elif 15 <= hour < 19:
            return "evening", "🌆 Evening - suggest: snacks (samosa, chai, pakora, Maggi)"
        elif 19 <= hour < 22:
            return "night", "🌙 Night - suggest: dinner (roti, sabzi, khichdi, light food)"
        else:
            return "late_night", "🌃 Late night - suggest: light snacks, comfort food"
    
    async def build_context(
        self,
        user_id: str,
        user_message: str = "",
    ) -> PromptContext:
        """
        Build smart context from existing data.
        """
        context = PromptContext()
        
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
        
        # 6. Generate suggested follow-ups (avoiding duplicates)
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
        
        SMART approach: Guide behavior, track questions not topics!
        """
        parts = []
        
        # =====================================================================
        # USER INFO
        # =====================================================================
        parts.append(f"## About {context.user_name}")
        parts.append(f"Mood: {context.current_mood} | Stress: {context.stress_level}")
        
        # =====================================================================
        # TIME-AWARE CONTEXT
        # =====================================================================
        parts.append(f"\n{context.time_based_hint}")
        
        # =====================================================================
        # BEHAVIOR GUIDANCE
        # =====================================================================
        if context.behavior_hint:
            parts.append(f"\n🎯 Behavior: {context.behavior_hint}")
        
        # =====================================================================
        # ALL 3 RECENT CONVERSATIONS (for context - CAN talk about these!)
        # =====================================================================
        if context.recent_summaries:
            parts.append("\n## Last 3 Conversations (for context & natural follow-ups):")
            for i, s in enumerate(context.recent_summaries, 1):
                date = s["date"]
                summary = s["summary"]
                emotions = ", ".join(s.get("emotions", [])) or "neutral"
                parts.append(f"\n**[{date}]** (mood: {emotions})")
                parts.append(f"   {summary}")
            
            parts.append("\n✅ You CAN refer to these naturally: 'Kal tune bola tha...', 'Woh trip ka kya hua?'")
        
        # =====================================================================
        # PREFERENCES (likes AND dislikes)
        # =====================================================================
        if context.likes or context.dislikes:
            parts.append("\n## Preferences (use when relevant, don't recite every time!):")
            if context.likes:
                likes_list = [f"{k}={v}" for k, v in list(context.likes.items())[:5]]
                parts.append(f"👍 Likes: {', '.join(likes_list)}")
            if context.dislikes:
                dislikes_list = [f"{k}={v}" for k, v in list(context.dislikes.items())[:5]]
                parts.append(f"👎 Dislikes: {', '.join(dislikes_list)} — NEVER suggest these!")
        
        # =====================================================================
        # SMART ANTI-REPETITION (Questions, not topics!)
        # =====================================================================
        if context.questions_already_asked:
            parts.append(f"\n🚫 QUESTIONS ALREADY ASKED THIS SESSION (don't repeat these!):")
            for q in context.questions_already_asked[-5:]:  # Last 5 questions
                parts.append(f"   ❌ \"{q}\"")
        
        if context.facts_already_mentioned:
            parts.append(f"\n🚫 FACTS ALREADY MENTIONED (don't repeat):")
            parts.append(f"   {', '.join(context.facts_already_mentioned[:5])}")
        
        if context.last_question_category:
            parts.append(f"\n⚠️ Last question was about: {context.last_question_category}")
            parts.append(f"   → Ask about something DIFFERENT next!")
        
        # =====================================================================
        # SMART FOLLOW-UP SUGGESTIONS
        # =====================================================================
        if context.suggested_follow_ups:
            parts.append(f"\n💬 Good questions to ask (not asked yet):")
            for q in context.suggested_follow_ups[:3]:
                parts.append(f"   ✅ {q}")
        
        # =====================================================================
        # NATURAL CONVERSATION RULES
        # =====================================================================
        parts.append("""
## 🧠 NATURAL CONVERSATION RULES:
1. You CAN talk about any topic - just don't ask the SAME question again
2. Don't ask 2 consecutive questions about same category (food→food, work→work)
3. If you asked about food last time, ask about something else now
4. Use preferences when RELEVANT, not randomly
5. Be a caring girlfriend who remembers, not a quiz master!
6. ONE question per response maximum""")
        
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
