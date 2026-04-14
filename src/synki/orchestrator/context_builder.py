"""
Context Builder - Smart, Human-like Context for AI Prompts

KEY FEATURES:
1. SMART MEMORY CATEGORIES (not just favorites!)
2. TOPIC ROTATION (family, hobbies, work, life, health)
3. Favorites used ONLY when user asks for suggestions
4. Human-like randomness
5. Anti-repetition tracking

MEMORY CATEGORIES:
- FAMILY: brother, sister, parents, relationships
- HOBBIES: badminton, PUBG, IPL, games
- WORK: office, meetings, projects
- LIFE: goals, plans, trips, events
- HEALTH: medicine, routine, fitness
- FAVORITES: food, movie (ONLY when asked!)
"""

import json
import random
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field

import structlog

# Import personalized context engine
from .personalized_context import PersonalizedContextEngine, UserBehaviorProfile, SessionIntelligence

logger = structlog.get_logger(__name__)


# ============================================================================
# SMART MEMORY CATEGORIES
# ============================================================================

MEMORY_CATEGORIES = {
    "FAMILY": {
        "keys": ["family_member", "relationship_status", "brother", "sister", "parents"],
        "questions": [
            "अनुराग से बात हुई?",
            "घर पर सब कैसे हैं?",
            "family के साथ कोई plan?",
        ],
        "weight": 15,  # How often to use this category
    },
    "HOBBIES": {
        "keys": ["hobby", "interest", "favorite_activity", "favorite_game", "favorite_team"],
        "questions": [
            "badminton खेला आजकल?",
            "PUBG में क्या हाल है?",
            "IPL देख रहे हो?",
        ],
        "weight": 20,
    },
    "LIFE": {
        "keys": ["event", "location", "birthday", "favorite_place"],
        "questions": [
            "trip का क्या plan है?",
            "वो plan आगे बढ़ा?",
            "कुछ नया हुआ life में?",
        ],
        "weight": 20,
    },
    "HEALTH": {
        "keys": ["health_condition", "daily_routine"],
        "questions": [
            "medicine ली आज?",
            "routine कैसा चल रहा?",
            "health कैसी है?",
        ],
        "weight": 10,
    },
    "MUSIC": {
        "keys": ["favorite_song", "favorite_drink"],
        "questions": [
            "वो गाना सुना आजकल?",
            "कोई नया music discover किया?",
        ],
        "weight": 10,
    },
    "FAVORITES": {
        "keys": ["favorite_food", "favorite_dish", "favorite_movie", "favorite_cuisine"],
        "questions": [],  # Empty - only suggest when ASKED
        "weight": 5,  # Very low - don't spam
    },
}


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
    time_of_day: str = "day"
    time_based_hint: str = ""
    
    # Recent chat messages from THIS session
    recent_chat_messages: list[dict] = field(default_factory=list)
    
    # ACTUAL recent conversations
    recent_conversations: list[dict] = field(default_factory=list)
    
    # Recent summaries
    recent_summaries: list[dict] = field(default_factory=list)
    
    # Quick summary of recent conversations
    recent_conversations_summary: str = ""
    
    # Daily summary
    daily_summary: dict = field(default_factory=dict)
    
    # Anti-repetition
    questions_already_asked: list[str] = field(default_factory=list)
    facts_already_mentioned: list[str] = field(default_factory=list)
    last_question_category: str = ""
    
    # Conversation FLOW tracking
    conversation_flow: list[str] = field(default_factory=list)
    
    # User preferences
    likes: dict = field(default_factory=dict)
    dislikes: dict = field(default_factory=dict)
    
    # ============ NEW: AVOID TOPICS (user is annoyed by these) ============
    avoid_topics: list[str] = field(default_factory=list)
    user_annoyances: list[str] = field(default_factory=list)
    
    # ============ NEW: SMART MEMORY CATEGORIES ============
    # All memories organized by category
    all_memories: dict = field(default_factory=dict)
    # Categories with actual data
    available_categories: list[str] = field(default_factory=list)
    # Current suggested topic category
    suggested_category: str = ""
    # Memory to reference for this turn
    suggested_memory: dict = field(default_factory=dict)
    
    # BEHAVIOR INSIGHTS
    happiness_triggers: list[str] = field(default_factory=list)
    stress_triggers: list[str] = field(default_factory=list)
    recent_activities: list[dict] = field(default_factory=list)
    
    # Behavior hints
    behavior_hint: str = ""
    suggested_follow_ups: list[str] = field(default_factory=list)
    contextual_suggestion: str = ""


class ContextBuilder:
    """
    Builds smart, human-like prompt context.
    
    SMART MEMORY USAGE:
    - Categorize ALL memories (family, hobbies, life, health, etc.)
    - Rotate between categories (don't always ask about same thing)
    - Use favorites ONLY when user asks "kya khau?" etc.
    
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
        
        # Session-level tracking (IN-MEMORY - for current session only)
        self._session_questions_asked: dict[str, list[str]] = {}  # user_id -> questions asked
        self._session_facts_mentioned: dict[str, set] = {}  # user_id -> facts mentioned
        self._session_last_question_category: dict[str, str] = {}  # user_id -> last category
        self._session_conversation_flow: dict[str, list[str]] = {}  # user_id -> last 5 topic categories
        
        # PERSISTENT tracking loaded from daily_summaries
        self._loaded_from_db: set[str] = set()  # user_ids that have been loaded
        
        # =====================================================
        # SESSION CACHE - Avoids DB hits on every turn!
        # Memories: Cached for entire session (don't change)
        # Profile: Cached for 60 seconds
        # Summaries: Cached for entire session
        # =====================================================
        self._cache: dict[str, dict] = {}  # user_id -> {memories, profile, summaries}
        self._cache_times: dict[str, dict] = {}  # user_id -> {memories_t, profile_t, summaries_t}
        self._PROFILE_CACHE_TTL = 60  # Refresh profile every 60 seconds
        
        logger.info("ContextBuilder initialized (with DB persistence + caching)")
    
    async def _load_persisted_questions(self, user_id: str):
        """
        Load questions from LAST 3 DAYS to prevent asking same questions!
        This is CRITICAL for anti-repetition across sessions.
        """
        if user_id in self._loaded_from_db:
            return  # Already loaded
        
        if not self._supabase:
            self._loaded_from_db.add(user_id)
            return
        
        try:
            from datetime import timedelta
            three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
            
            # Load from LAST 3 DAYS - not just today!
            result = self._supabase.table("daily_summaries")\
                .select("questions_asked, topics_discussed, favorites_mentioned, last_topic, date")\
                .eq("user_id", user_id)\
                .gte("date", three_days_ago)\
                .order("date", desc=True)\
                .execute()
            
            if result.data:
                all_questions = []
                all_topics = []
                all_favorites = set()
                last_topic = ""
                
                for summary in result.data:
                    # Collect questions from all days
                    questions = summary.get("questions_asked", [])
                    if questions and isinstance(questions, list):
                        all_questions.extend(questions)
                    
                    # Collect topics
                    topics = summary.get("topics_discussed", [])
                    if topics and isinstance(topics, list):
                        all_topics.extend(topics)
                    
                    # Collect favorites mentioned
                    favorites = summary.get("favorites_mentioned", [])
                    if favorites and isinstance(favorites, list):
                        all_favorites.update(favorites)
                    
                    # Last topic from most recent day
                    if not last_topic:
                        last_topic = summary.get("last_topic", "")
                
                # Store all questions in session
                if all_questions:
                    if user_id not in self._session_questions_asked:
                        self._session_questions_asked[user_id] = []
                    self._session_questions_asked[user_id].extend(all_questions)
                    logger.info(f"📚 Loaded {len(all_questions)} questions from LAST 3 DAYS for anti-repetition")
                
                if all_topics:
                    if user_id not in self._session_conversation_flow:
                        self._session_conversation_flow[user_id] = []
                    self._session_conversation_flow[user_id].extend(all_topics[-10:])
                
                if all_favorites:
                    if user_id not in self._session_facts_mentioned:
                        self._session_facts_mentioned[user_id] = set()
                    self._session_facts_mentioned[user_id].update(all_favorites)
                    logger.info(f"📚 Loaded {len(all_favorites)} favorites from last 3 days")
                
                if last_topic:
                    self._session_last_question_category[user_id] = last_topic
            
            self._loaded_from_db.add(user_id)
            
        except Exception as e:
            logger.warning(f"Could not load persisted questions: {e}")
            self._loaded_from_db.add(user_id)
    
    async def persist_question_to_db(self, user_id: str, question: str):
        """Persist a question to daily_summaries so it survives agent restart"""
        if not self._supabase:
            return
        
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            
            # Check if today's summary exists
            result = self._supabase.table("daily_summaries")\
                .select("id, questions_asked")\
                .eq("user_id", user_id)\
                .eq("date", date)\
                .execute()
            
            if result.data:
                # Update existing
                existing_questions = result.data[0].get("questions_asked", []) or []
                if question.lower() not in [q.lower() for q in existing_questions]:
                    existing_questions.append(question)
                    self._supabase.table("daily_summaries")\
                        .update({"questions_asked": existing_questions})\
                        .eq("id", result.data[0]["id"])\
                        .execute()
            else:
                # Create new
                self._supabase.table("daily_summaries").insert({
                    "user_id": user_id,
                    "date": date,
                    "questions_asked": [question],
                    "topics_discussed": [],
                    "activities": [],
                    "dominant_mood": "neutral"
                }).execute()
                
            logger.debug(f"Persisted question to daily_summary: {question[:30]}...")
            
        except Exception as e:
            logger.warning(f"Could not persist question: {e}")
    
    async def persist_favorite_to_db(self, user_id: str, favorite: str):
        """Persist a mentioned favorite to daily_summaries so it survives agent restart"""
        if not self._supabase:
            return
        
        # Track in memory immediately
        if user_id not in self._session_facts_mentioned:
            self._session_facts_mentioned[user_id] = set()
        self._session_facts_mentioned[user_id].add(favorite.lower())
        
        # Try to persist to DB (column may not exist yet)
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            result = self._supabase.table("daily_summaries")\
                .select("id, favorites_mentioned")\
                .eq("user_id", user_id)\
                .eq("date", date)\
                .execute()
            
            if result.data:
                existing = result.data[0].get("favorites_mentioned", []) or []
                if favorite.lower() not in [f.lower() for f in existing]:
                    existing.append(favorite)
                    self._supabase.table("daily_summaries")\
                        .update({"favorites_mentioned": existing})\
                        .eq("id", result.data[0]["id"])\
                        .execute()
                
            logger.debug(f"Persisted favorite to daily_summary: {favorite}")
            
        except Exception as e:
            # Column might not exist yet - that's okay, in-memory tracking still works
            logger.debug(f"Could not persist favorite (column may not exist): {e}")
    
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
        
        OPTIMIZED: All DB calls run in PARALLEL for 5x faster context building!
        
        Args:
            user_id: User's unique ID
            user_message: Current user message
            recent_messages: List of recent chat messages from current session
                            [{"role": "user"|"assistant", "content": "..."}]
        """
        import asyncio
        
        context = PromptContext()
        
        # Store recent chat messages (no DB call)
        if recent_messages:
            context.recent_chat_messages = recent_messages[-30:]
        
        # 1. Time context (no DB call)
        context.time_of_day, context.time_based_hint = self.get_time_context()
        
        # =====================================================
        # PARALLEL DB CALLS - This was the main bottleneck!
        # Before: 6 sequential calls = 6 * ~100ms = 600ms
        # After: All parallel = ~100ms total
        # =====================================================
        (
            _,  # load_persisted_questions returns None
            memories,
            short_term,
            recent_convos,
            summaries,
            daily_summary,
        ) = await asyncio.gather(
            self._load_persisted_questions(user_id),
            self._get_memories(user_id),
            self._get_short_term_profile(user_id),
            self._get_recent_conversations(user_id),
            self._get_recent_summaries(user_id),
            self._get_daily_summary(user_id),
            return_exceptions=True,  # Don't fail if one query fails
        )
        
        # Handle potential exceptions from gather
        if isinstance(memories, Exception):
            logger.warning(f"memories fetch failed: {memories}")
            memories = {}
        if isinstance(short_term, Exception):
            logger.warning(f"short_term fetch failed: {short_term}")
            short_term = {}
        if isinstance(recent_convos, Exception):
            logger.warning(f"recent_convos fetch failed: {recent_convos}")
            recent_convos = []
        if isinstance(summaries, Exception):
            logger.warning(f"summaries fetch failed: {summaries}")
            summaries = []
        if isinstance(daily_summary, Exception):
            logger.warning(f"daily_summary fetch failed: {daily_summary}")
            daily_summary = {}
        
        # 2. Process memories
        if memories:
            context.user_name = memories.get("name", "Baby")
            context.likes, context.dislikes = self._extract_preferences(memories)
            
            # EXTRACT AVOID TOPICS
            context.avoid_topics, context.user_annoyances = self._extract_avoid_topics(memories)
            
            # CATEGORIZE ALL MEMORIES
            context.all_memories = self._categorize_memories(memories)
            context.available_categories = [
                cat for cat, mems in context.all_memories.items() 
                if mems and cat != "FAVORITES"
            ]
            
            # Pick a topic category intelligently
            context.suggested_category = self._pick_topic_category(
                available=context.available_categories,
                recent_flow=context.conversation_flow,
                mood=context.current_mood,
            )
            
            if context.suggested_category and context.all_memories.get(context.suggested_category):
                context.suggested_memory = random.choice(context.all_memories[context.suggested_category])
        
        # 3. Process short-term profile
        if short_term:
            context.current_mood = short_term.get("dominant_mood", "neutral")
            context.stress_level = short_term.get("stress_level", "low")
            context.behavior_hint = self._get_behavior_hint(
                context.current_mood,
                context.stress_level
            )
            context.happiness_triggers = short_term.get("recent_happiness_triggers", [])
            context.stress_triggers = short_term.get("recent_stress_triggers", [])
            context.recent_activities = short_term.get("recent_activities", [])
        
        # 4. Process recent conversations
        context.recent_conversations = recent_convos if isinstance(recent_convos, list) else []
        
        # 4b. Process summaries
        context.recent_summaries = [
            {
                "conversation_date": s.get("conversation_date", "unknown"),
                "summary": s.get("summary", ""),
                "topics": s.get("topics", []),
                "emotions": s.get("emotions_detected", []),
            }
            for s in (summaries if isinstance(summaries, list) else [])
        ]
        
        # 4c. FALLBACK
        if not context.recent_summaries and context.recent_conversations:
            context.recent_conversations_summary = self._create_quick_summary(context.recent_conversations)
        
        # 5. Process daily summary
        context.daily_summary = daily_summary if isinstance(daily_summary, dict) else {}
        
        # 6. SMART anti-repetition
        context.questions_already_asked = self._session_questions_asked.get(user_id, [])
        context.facts_already_mentioned = list(self._session_facts_mentioned.get(user_id, set()))
        context.last_question_category = self._session_last_question_category.get(user_id, "")
        
        # 7. Conversation FLOW tracking
        context.conversation_flow = self._session_conversation_flow.get(user_id, [])
        
        # 8. SMART contextual suggestion
        context.contextual_suggestion = self._get_smart_suggestion(
            time_of_day=context.time_of_day,
            mood=context.current_mood,
            stress=context.stress_level,
            conversation_flow=context.conversation_flow,
            questions_asked=context.questions_already_asked,
        )
        
        # 9. Generate suggested follow-ups
        context.suggested_follow_ups = self._generate_smart_followups(
            context, user_message
        )
        
        return context
    
    def _categorize_memories(self, memories: dict) -> dict[str, list[dict]]:
        """
        Categorize all user memories into smart categories.
        
        Returns dict like:
        {
            "FAMILY": [{"key": "brother", "value": "अनुराग"}, ...],
            "HOBBIES": [{"key": "hobby", "value": "badminton"}, ...],
            ...
        }
        """
        categorized = {cat: [] for cat in MEMORY_CATEGORIES.keys()}
        
        facts = memories.get("facts", [])
        if not facts:
            return categorized
        
        for fact in facts:
            key = fact.get("key", "").lower()
            value = fact.get("value", "")
            
            # Find which category this fact belongs to
            for cat_name, cat_info in MEMORY_CATEGORIES.items():
                if any(k in key for k in cat_info["keys"]):
                    categorized[cat_name].append({
                        "key": fact.get("key"),
                        "value": value,
                        "category": cat_name,
                    })
                    break
        
        return categorized
    
    def _pick_topic_category(
        self,
        available: list[str],
        recent_flow: list[str],
        mood: str = "neutral",
    ) -> str:
        """
        Pick a topic category intelligently.
        
        Rules:
        - Avoid recently discussed categories
        - Weight based on mood (sad = LIFE, FAMILY; happy = HOBBIES)
        - Never spam FAVORITES
        """
        if not available:
            return ""
        
        # Categories discussed in last 3 turns
        avoid = set(recent_flow[-3:]) if recent_flow else set()
        
        # Filter available categories
        choices = [c for c in available if c not in avoid]
        if not choices:
            choices = available  # Reset if all used
        
        # Mood-based weights
        if mood in ["sad", "stressed", "tired"]:
            # More FAMILY, LIFE when sad
            weight_boost = {"FAMILY": 3, "LIFE": 2, "HOBBIES": 1}
        elif mood in ["happy", "excited"]:
            # More HOBBIES, MUSIC when happy
            weight_boost = {"HOBBIES": 3, "MUSIC": 2, "LIFE": 1}
        else:
            weight_boost = {}
        
        # Build weighted choices
        weighted = []
        for cat in choices:
            base_weight = MEMORY_CATEGORIES.get(cat, {}).get("weight", 10)
            boost = weight_boost.get(cat, 1)
            weighted.extend([cat] * (base_weight * boost))
        
        if weighted:
            return random.choice(weighted)
        return random.choice(choices) if choices else ""
    
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
    
    async def track_question_asked_async(self, user_id: str, question: str):
        """Track a question AND persist to DB (use this for persistence)"""
        self.track_question_asked(user_id, question)
        await self.persist_question_to_db(user_id, question)
    
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
        Format context for LLM - SMART MEMORY USAGE!
        
        Key features:
        1. Uses ALL memory categories (family, hobbies, life, etc.)
        2. Rotates topics intelligently
        3. Favorites ONLY when user asks for suggestions
        4. Varied response modes
        """
        from datetime import datetime
        parts = []
        
        hour = datetime.now().hour
        topics_done = list(context.conversation_flow) if context.conversation_flow else []
        mood = context.current_mood
        
        # ========== DYNAMIC RESPONSE MODE ==========
        if mood in ["sad", "stressed", "tired"]:
            weights = {"REACT": 55, "COMFORT": 25, "SHARE": 12, "LISTEN": 8}
        elif mood in ["happy", "excited"]:
            weights = {"REACT": 35, "TEASE": 20, "FLIRT": 15, "ASK_LIFE": 15, "CURIOUS": 15}
        elif mood == "bored":
            weights = {"TEASE": 20, "ASK_LIFE": 25, "CURIOUS": 20, "REACT": 20, "SUGGEST": 15}
        elif len(topics_done) >= 4:
            weights = {"REACT": 60, "TEASE": 15, "FLIRT": 15, "SHARE": 10}
        else:
            weights = {"REACT": 40, "TEASE": 15, "ASK_LIFE": 20, "SHARE": 15, "CURIOUS": 10}
        
        choices = []
        for mode, weight in weights.items():
            choices.extend([mode] * weight)
        response_mode = random.choice(choices)
        
        # ========== HEADER ==========
        parts.append(f"👤 {context.user_name} | Mood: {mood}")
        
        # ========== MODE INSTRUCTION ==========
        parts.append(f"\n🎲 THIS TURN: {response_mode}")
        
        mode_instructions = {
            "REACT": "→ Just react: 'achaaa', 'ohh', 'hmm', 'sachi?' NO question!",
            "TEASE": "→ Tease playfully 😏 'ohooo hero ban gaye'",
            "FLIRT": "→ Say something sweet 💕 'cute ho tum', 'miss kiya'",
            "SHARE": "→ Share about YOURSELF: 'main bhi bore', 'mera bhi same'",
            "CURIOUS": "→ Ask follow-up: 'phir kya hua?', 'kyun?', 'kaise?'",
            "COMFORT": "→ Be supportive: 'main hoon na', 'koi nahi'",
            "LISTEN": "→ Just listen: 'hmm', 'haan', 'acha'",
            "SUGGEST": "→ Suggest activity: 'chal movie dekhte', 'game khelte hain'",
            "ASK_LIFE": "→ Ask about THEIR LIFE (see topic below)",
        }
        parts.append(mode_instructions.get(response_mode, "→ React naturally"))
        
        # ========== SMART TOPIC SUGGESTION (from memories!) ==========
        if response_mode == "ASK_LIFE" and context.suggested_category and context.suggested_memory:
            cat = context.suggested_category
            mem = context.suggested_memory
            
            parts.append(f"\n🎯 ASK ABOUT: {cat}")
            parts.append(f"   Memory: {mem.get('key')}: {mem.get('value')}")
            
            # Category-specific suggestions
            if cat == "FAMILY":
                parts.append("   → Ask: 'अनुराग से बात हुई?', 'family कैसी है?', 'trip plan हुआ?'")
            elif cat == "HOBBIES":
                parts.append("   → Ask: 'badminton खेला?', 'PUBG khela?', 'IPL kaisa chal raha?'")
            elif cat == "LIFE":
                parts.append("   → Ask: 'trip ka plan?', 'कोई नया update?', 'plan आगे बढ़ा?'")
            elif cat == "HEALTH":
                parts.append("   → Ask (gently): 'medicine li?', 'routine kaisa hai?'")
            elif cat == "MUSIC":
                parts.append("   → Ask: 'कोई नया song discover किया?', 'music sun rahe ho?'")
        
        # ========== ALL MEMORIES BY CATEGORY (for reference) ==========
        if context.all_memories and response_mode in ["ASK_LIFE", "CURIOUS", "SUGGEST"]:
            parts.append("\n📚 USER'S LIFE (pick ONE topic, be specific!):")
            
            for cat, mems in context.all_memories.items():
                if mems and cat != "FAVORITES":  # Never show favorites
                    # Show 2 memories from each category
                    sample = mems[:2]
                    mem_str = ", ".join([f"{m['key']}: {m['value']}" for m in sample])
                    parts.append(f"  {cat}: {mem_str}")
        
        # ========== USER DISLIKES & AVOID TOPICS ==========
        # Use pre-computed avoid_topics from context (populated in build_context)
        avoid_topics = list(context.avoid_topics) if context.avoid_topics else []
        dislikes = []
        
        # Also check all_memories for dislikes and annoyances
        if context.all_memories:
            for cat, mems in context.all_memories.items():
                for mem in mems:
                    key = mem.get("key", "").lower()
                    value = str(mem.get("value", "")).lower()
                    mem_type = mem.get("type", "").lower()
                    
                    # Check for emotional states showing annoyance
                    if "emotional_state" in key:
                        if "irritat" in value or "annoy" in value or "bore" in value:
                            if "movie" in value:
                                avoid_topics.append("movie")
                            if "food" in value or "khana" in value:
                                avoid_topics.append("food")
                    
                    # Check for explicit dislikes
                    if mem_type == "dislike" or "dislike" in key or "hate" in key:
                        dislikes.append(f"{key}: {value}")
        
        # Also add user_annoyances if present
        if context.user_annoyances:
            for annoy in context.user_annoyances[:3]:
                dislikes.append(f"User expressed: {annoy}")
        
        if avoid_topics or dislikes:
            parts.append("\n🚫 USER PREFERENCES (IMPORTANT!):")
            if avoid_topics:
                unique_topics = list(set(avoid_topics))
                parts.append(f"   ⚠️ AVOID these topics: {', '.join(unique_topics)}")
            if dislikes:
                parts.append("   User dislikes/annoyances:")
                for d in dislikes[:3]:
                    parts.append(f"   ❌ {d}")
        
        # ========== RECENT CHAT ==========
        if context.recent_chat_messages:
            parts.append("\n💬 Recent:")
            for msg in context.recent_chat_messages[-4:]:
                role = "U" if msg.get("role") == "user" else "AI"
                content = msg.get("content", msg.get("text", ""))[:40]
                parts.append(f"  {role}: {content}")
        
        # ========== ANTI-REPETITION (MUCH STRONGER!) ==========
        if context.questions_already_asked:
            # Get ALL recent questions (not just 5)
            all_q = context.questions_already_asked
            parts.append("\n🚫🚫🚫 CRITICAL - DON'T ASK ABOUT THESE TOPICS AGAIN! 🚫🚫🚫")
            
            # Extract question TOPICS to avoid - be comprehensive!
            forbidden_topics = set()
            for q in all_q:
                q_lower = q.lower()
                # Trip/travel related - USER COMPLAINED ABOUT THIS!
                if any(w in q_lower for w in ["trip", "travel", "घूम", "जाना", "vacation", "holiday", "plan"]):
                    forbidden_topics.add("TRIP/TRAVEL/PLANS")
                if any(w in q_lower for w in ["खाना", "khana", "food", "khaya", "खाया"]):
                    forbidden_topics.add("FOOD")
                if any(w in q_lower for w in ["movie", "film", "फिल्म"]):
                    forbidden_topics.add("MOVIE")
                if any(w in q_lower for w in ["कैसे हो", "कैसा", "kaise ho", "kaisa"]):
                    forbidden_topics.add("HOW ARE YOU")
                if any(w in q_lower for w in ["ipl", "cricket", "match", "team"]):
                    forbidden_topics.add("IPL/CRICKET")
                if any(w in q_lower for w in ["pubg", "game", "खेल"]):
                    forbidden_topics.add("GAMES")
                if any(w in q_lower for w in ["family", "घर", "parents", "brother", "sister"]):
                    forbidden_topics.add("FAMILY")
            
            if forbidden_topics:
                parts.append(f"   ❌❌ FORBIDDEN: {', '.join(forbidden_topics)}")
                parts.append("   ⚠️ User will get ANNOYED if you ask about these again!")
            
            # Show last 5 specific questions
            parts.append("   Recent questions (DO NOT REPEAT):")
            for q in all_q[-5:]:
                parts.append(f"   ❌ {q[:50]}")
        
        # ========== FOOD REQUEST DETECTION ==========
        last_user_msg = ""
        if context.recent_chat_messages:
            for msg in reversed(context.recent_chat_messages):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", msg.get("text", "")).lower()
                    break
        
        food_patterns = [
            "kya khau", "kya khaun", "kya khaye", "khana", "khane",
            "hungry", "bhukh", "bhook", "food suggest", "suggest food",
            "dinner", "lunch", "breakfast", "snack", "chai", "coffee",
            "suggest karo", "batao kya", "kuch khana", "order karu",
            "खाऊं", "खाना", "भूख", "सजेस्ट"
        ]
        
        is_food_request = any(p in last_user_msg for p in food_patterns)
        
        if is_food_request:
            # Import and use smart food suggestion
            from synki.orchestrator.persona_engine import get_smart_food_suggestion
            
            # Get user favorites if available
            user_favs = {}
            if context.all_memories and "FAVORITES" in context.all_memories:
                for mem in context.all_memories["FAVORITES"]:
                    if "food" in mem.get("key", "").lower() or "dish" in mem.get("key", "").lower():
                        user_favs["food"] = mem.get("value", "")
            
            suggestion, suggestion_type = get_smart_food_suggestion(user_favs)
            
            parts.append(f"\n🍽️ FOOD REQUEST DETECTED!")
            parts.append(f"   Suggest: '{suggestion}' ({suggestion_type})")
            if suggestion_type == "favorite":
                parts.append("   → Use this exact line or similar!")
            elif suggestion_type == "related":
                parts.append("   → Suggest something related but new!")
            else:
                parts.append("   → Be adventurous, try something new!")
        
        # ========== RULES ==========
        parts.append("\n⚠️ RULES:")
        if not is_food_request:
            parts.append("  1. NEVER mention food/movie unless user asks")
        parts.append("  2. Ask about LIFE (family/hobbies/work), not favorites")
        parts.append("  3. 1-2 sentences max")
        
        if hour >= 22 or hour < 6:
            parts.append("\n🌙 Late - be soft, short")
        
        return "\n".join(parts)
    
    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================
    
    async def _get_memories(self, user_id: str) -> dict:
        """Get memories from database (CACHED for entire session)"""
        import time
        
        # Check cache first
        if user_id in self._cache and "memories" in self._cache[user_id]:
            return self._cache[user_id]["memories"]
        
        if not self._supabase:
            return {}
        
        try:
            result = self._supabase.table("memories")\
                .select("name, facts, preferences")\
                .eq("user_id", user_id)\
                .execute()
            data = result.data[0] if result.data else {}
            
            # Cache it
            if user_id not in self._cache:
                self._cache[user_id] = {}
            self._cache[user_id]["memories"] = data
            
            return data
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return {}
    
    async def _get_short_term_profile(self, user_id: str) -> dict:
        """Get short-term profile from database (CACHED for 60s)"""
        import time
        
        # Check cache with TTL
        if user_id in self._cache and "profile" in self._cache[user_id]:
            cache_time = self._cache_times.get(user_id, {}).get("profile", 0)
            if time.time() - cache_time < self._PROFILE_CACHE_TTL:
                return self._cache[user_id]["profile"]
        
        if not self._supabase:
            return {}
        
        try:
            result = self._supabase.table("user_profiles_short_term")\
                .select("profile_data")\
                .eq("user_id", user_id)\
                .execute()
            data = result.data[0].get("profile_data", {}) if result.data else {}
            
            # Cache it with timestamp
            if user_id not in self._cache:
                self._cache[user_id] = {}
            if user_id not in self._cache_times:
                self._cache_times[user_id] = {}
            self._cache[user_id]["profile"] = data
            self._cache_times[user_id]["profile"] = time.time()
            
            return data
        except Exception as e:
            logger.error(f"Failed to get short-term profile: {e}")
            return {}
    
    async def _get_recent_summaries(self, user_id: str) -> list[dict]:
        """Get ALL 3 recent conversation summaries (CACHED for session)"""
        # Check cache first
        if user_id in self._cache and "summaries" in self._cache[user_id]:
            return self._cache[user_id]["summaries"]
        
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.table("conversation_summaries")\
                .select("summary, topics, emotions_detected, conversation_date")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(self.MAX_SUMMARIES_IN_PROMPT)\
                .execute()
            data = result.data or []
            
            # Cache it
            if user_id not in self._cache:
                self._cache[user_id] = {}
            self._cache[user_id]["summaries"] = data
            
            return data
        except Exception as e:
            logger.error(f"Failed to get summaries: {e}")
            return []
    
    async def _get_recent_conversations(self, user_id: str) -> list[dict]:
        """
        Get ACTUAL recent conversations (real messages!) from last 3 days.
        CACHED FOR SESSION - doesn't change during conversation.
        """
        # Check cache first
        if user_id in self._cache and "recent_convos" in self._cache[user_id]:
            return self._cache[user_id]["recent_convos"]
        
        if not self._supabase:
            return []
        
        try:
            from datetime import datetime, timedelta
            three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
            
            # Get last 50 messages from recent days (more context!)
            result = self._supabase.table("chat_history")\
                .select("role, content, created_at")\
                .eq("user_id", user_id)\
                .gte("created_at", three_days_ago)\
                .order("created_at", desc=True)\
                .limit(50)\
                .execute()
            
            if not result.data:
                return []
            
            # Group by date
            conversations_by_date = {}
            for msg in reversed(result.data):  # Oldest first
                date = msg["created_at"][:10]  # YYYY-MM-DD
                if date not in conversations_by_date:
                    conversations_by_date[date] = []
                conversations_by_date[date].append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Return last 3 days with messages (8 messages each for more context)
            recent_convos = []
            for date in sorted(conversations_by_date.keys(), reverse=True)[:3]:
                recent_convos.append({
                    "date": date,
                    "messages": conversations_by_date[date][-8:]  # Last 8 messages per day!
                })
            
            # Cache it
            if user_id not in self._cache:
                self._cache[user_id] = {}
            self._cache[user_id]["recent_convos"] = recent_convos
            
            logger.info(f"📜 Loaded {len(recent_convos)} days of recent conversations (cached)")
            return recent_convos
            
        except Exception as e:
            logger.error(f"Failed to get recent conversations: {e}")
            return []
    
    async def _get_daily_summary(self, user_id: str) -> dict:
        """Get most recent daily summary (today or yesterday) - CACHED for 60s"""
        import time
        
        # Check cache with TTL (daily summary can change during conversation)
        if user_id in self._cache and "daily_summary" in self._cache[user_id]:
            cache_time = self._cache_times.get(user_id, {}).get("daily_summary", 0)
            if time.time() - cache_time < self._PROFILE_CACHE_TTL:
                return self._cache[user_id]["daily_summary"]
        
        if not self._supabase:
            return {}
        
        try:
            from datetime import date, timedelta
            today = date.today()
            yesterday = today - timedelta(days=1)
            
            # Try TODAY first, then YESTERDAY
            for check_date in [today, yesterday]:
                result = self._supabase.table("daily_summaries")\
                    .select("*")\
                    .eq("user_id", user_id)\
                    .eq("date", check_date.isoformat())\
                    .execute()
                
                if result.data:
                    data = result.data[0]
                    parsed = {
                        "date": data.get("date"),
                        "dominant_mood": data.get("dominant_mood", "neutral"),
                        "topics_discussed": data.get("topics_discussed", []),
                        "questions_asked": data.get("questions_asked", []),
                        "activities": data.get("activities", []),
                        "highlights": data.get("highlights", []),
                        "concerns": data.get("concerns", []),
                        "last_topic": data.get("last_topic"),
                        "conversation_ended_on": data.get("conversation_ended_on"),
                    }
                    
                    # Cache it
                    if user_id not in self._cache:
                        self._cache[user_id] = {}
                    if user_id not in self._cache_times:
                        self._cache_times[user_id] = {}
                    self._cache[user_id]["daily_summary"] = parsed
                    self._cache_times[user_id]["daily_summary"] = time.time()
                    
                    logger.info(f"📅 Loaded daily summary for {check_date} (cached)")
                    return parsed
            
            logger.info(f"📅 No daily summary found for {today} or {yesterday}")
            return {}
        except Exception as e:
            logger.error(f"Failed to get daily summary: {e}")
            return {}
    
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
    
    def _extract_avoid_topics(self, memories: dict) -> tuple[list[str], list[str]]:
        """
        Extract topics user is annoyed by or wants to avoid.
        
        Returns:
            (avoid_topics, user_annoyances)
        """
        avoid_topics = []
        user_annoyances = []
        
        facts = memories.get("facts", [])
        for fact in facts:
            key = fact.get("key", "").lower()
            value = str(fact.get("value", "")).lower()
            
            # Check for explicit annoyance/avoid patterns
            annoyance_keywords = ["irritat", "annoy", "bored", "tired of", "don't want", "nahi chahiye", "band karo", "stop asking"]
            if any(kw in key or kw in value for kw in annoyance_keywords):
                user_annoyances.append(fact.get("value", ""))
                # Extract the topic from the annoyance
                if "movie" in value or "film" in value:
                    avoid_topics.append("movie")
                if "food" in value or "khana" in value or "khao" in value:
                    avoid_topics.append("food_suggestions")
                if "work" in value or "job" in value or "office" in value:
                    avoid_topics.append("work")
            
            # Check for emotional states that indicate avoidance
            if "emotional_state" in key:
                user_annoyances.append(value)
                # Parse what they're irritated about
                if "movie" in value:
                    avoid_topics.append("movie")
                if "same" in value and ("question" in value or "topic" in value):
                    avoid_topics.append("repetitive_questions")
            
            # Check for dislikes
            if "dislike" in key or "hate" in key or "avoid" in key:
                avoid_topics.append(fact.get("value", ""))
        
        # Remove duplicates
        avoid_topics = list(set(avoid_topics))
        user_annoyances = list(set(user_annoyances))
        
        return avoid_topics, user_annoyances
    
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
    
    def _create_quick_summary(self, conversations: list[dict]) -> str:
        """
        Create a quick summary from raw conversation messages.
        Used as fallback when no LLM summaries exist.
        """
        if not conversations:
            return ""
        
        # Collect all user messages
        user_messages = []
        for conv in conversations:
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    user_messages.append(msg.get("content", ""))
        
        if not user_messages:
            return ""
        
        all_text = " ".join(user_messages).lower()
        
        # Extract key items
        summary_parts = []
        
        # Food items
        food_words = ["कढ़ाई पनीर", "पनीर", "बिरयानी", "खाना", "lunch", "dinner", "chai", 
                      "kadhai", "paneer", "biryani", "food", "restaurant", "रेस्टोरेंट"]
        found_foods = [f for f in food_words if f in all_text]
        if found_foods:
            summary_parts.append(f"Food: {', '.join(found_foods[:3])}")
        
        # Places
        place_words = ["करवाली", "मनाली", "office", "ऑफिस", "घर", "manali", "delhi"]
        found_places = [p for p in place_words if p in all_text]
        if found_places:
            summary_parts.append(f"Places: {', '.join(found_places[:3])}")
        
        # Activities/Plans
        if "जाने वाले" in all_text or "करने वाले" in all_text or "try" in all_text:
            summary_parts.append("Had plans to do something")
        if "meeting" in all_text or "मीटिंग" in all_text:
            summary_parts.append("Had meeting")
        if "trip" in all_text or "यात्रा" in all_text:
            summary_parts.append("Discussed trip plans")
        
        # If found specific items
        if "कढ़ाई पनीर" in all_text or "kadhai paneer" in all_text:
            summary_parts.append("Discussed trying kadhai paneer")
        if "करवाली" in all_text or "karwali" in all_text:
            summary_parts.append("Mentioned Karwali restaurant")
        
        if summary_parts:
            return " | ".join(summary_parts)
        else:
            # Return first few user messages as context
            return f"Recent: {user_messages[0][:100]}..."
    
    def _extract_key_items_from_conversations(self, conversations: list[dict]) -> list[str]:
        """
        Extract KEY SPECIFIC items from raw conversations.
        Food, places, activities, plans - no filler!
        """
        import re
        key_items = []
        
        # Patterns to extract specific things
        food_patterns = [
            r'(कढ़ाई पनीर|पनीर बटर मसाला|मटर चाप|बिरयानी|मैगी|दाल|रोटी|चावल|समोसा|चाय|कॉफी)',
            r'(kadhai paneer|paneer|biryani|maggi|dal|roti|samosa|chai|coffee|matar chap)',
        ]
        place_patterns = [
            r'(करवाली|मनाली|दिल्ली|मुंबई|ऑफिस|घर|रेस्टोरेंट)',
            r'(karwali|manali|delhi|mumbai|office|home|restaurant)',
        ]
        activity_patterns = [
            r'(मीटिंग|ट्रिप|यात्रा|फिल्म|मूवी|खाना|आराम)',
            r'(meeting|trip|travel|movie|film|food|rest)',
        ]
        
        all_text = ""
        for conv in conversations:
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    all_text += " " + msg.get("content", "")
        
        all_text_lower = all_text.lower()
        
        # Extract foods
        for pattern in food_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for m in matches:
                item = f"Food mentioned: {m}"
                if item not in key_items:
                    key_items.append(item)
        
        # Extract places
        for pattern in place_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            for m in matches:
                item = f"Place: {m}"
                if item not in key_items:
                    key_items.append(item)
        
        # Look for plans (keywords)
        if "जाने वाले" in all_text or "करने वाले" in all_text or "try" in all_text_lower:
            key_items.append("Had plans to try something")
        
        if "कढ़ाई पनीर" in all_text or "kadhai" in all_text_lower:
            key_items.append("Discussed trying kadhai paneer")
        
        if "रेस्टोरेंट" in all_text or "restaurant" in all_text_lower:
            key_items.append("Talked about going to restaurant")
        
        return key_items[:8]
