"""
Context Builder - Smart, Human-like Context for AI Prompts

KEY FEATURES:
1. PERSONALIZED behavior tracking (happiness/stress triggers)
2. DYNAMIC response modes (REACT 60%, FOLLOW_UP 25%, NEW_TOPIC 10%, RANDOM 5%)
3. Topic rotation with tracking
4. Favorites used ONLY when mood needs cheering
5. Time-based energy awareness
6. Human-like randomness

NO extra storage - just smart formatting of existing data!
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
    
    # ACTUAL recent conversations (last 3 sessions with real messages!)
    recent_conversations: list[dict] = field(default_factory=list)
    
    # Recent summaries from PREVIOUS sessions (last 3 sessions) - backup
    recent_summaries: list[dict] = field(default_factory=list)
    
    # Quick summary of recent conversations (fallback when no summaries exist)
    recent_conversations_summary: str = ""
    
    # Daily summary (today/yesterday full day context)
    daily_summary: dict = field(default_factory=dict)
    
    # SMART Anti-repetition (questions, not topics!)
    questions_already_asked: list[str] = field(default_factory=list)
    facts_already_mentioned: list[str] = field(default_factory=list)
    last_question_category: str = ""  # To prevent consecutive similar questions
    
    # Conversation FLOW tracking (last few topics discussed)
    conversation_flow: list[str] = field(default_factory=list)  # Last 5 topic categories
    
    # User preferences
    likes: dict = field(default_factory=dict)
    dislikes: dict = field(default_factory=dict)
    
    # BEHAVIOR INSIGHTS (from short-term profile)
    happiness_triggers: list[str] = field(default_factory=list)
    stress_triggers: list[str] = field(default_factory=list)
    recent_activities: list[dict] = field(default_factory=list)
    
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
        
        # Session-level tracking (IN-MEMORY - for current session only)
        self._session_questions_asked: dict[str, list[str]] = {}  # user_id -> questions asked
        self._session_facts_mentioned: dict[str, set] = {}  # user_id -> facts mentioned
        self._session_last_question_category: dict[str, str] = {}  # user_id -> last category
        self._session_conversation_flow: dict[str, list[str]] = {}  # user_id -> last 5 topic categories
        
        # PERSISTENT tracking loaded from daily_summaries
        self._loaded_from_db: set[str] = set()  # user_ids that have been loaded
        
        logger.info("ContextBuilder initialized (with DB persistence)")
    
    async def _load_persisted_questions(self, user_id: str):
        """
        Load questions from today's daily_summary when agent restarts.
        This prevents asking the same questions again!
        """
        if user_id in self._loaded_from_db:
            return  # Already loaded
        
        if not self._supabase:
            self._loaded_from_db.add(user_id)
            return
        
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            result = self._supabase.table("daily_summaries")\
                .select("questions_asked, topics_discussed, last_topic")\
                .eq("user_id", user_id)\
                .eq("date", date)\
                .execute()
            
            if result.data:
                summary = result.data[0]
                
                # Load questions already asked today
                questions = summary.get("questions_asked", [])
                if questions and isinstance(questions, list):
                    if user_id not in self._session_questions_asked:
                        self._session_questions_asked[user_id] = []
                    self._session_questions_asked[user_id].extend(questions)
                    logger.info(f"Loaded {len(questions)} questions from daily_summary for {user_id}")
                
                # Load topics discussed
                topics = summary.get("topics_discussed", [])
                if topics and isinstance(topics, list):
                    if user_id not in self._session_conversation_flow:
                        self._session_conversation_flow[user_id] = []
                    self._session_conversation_flow[user_id].extend(topics[-5:])
                
                # Load favorites already mentioned today
                favorites = summary.get("favorites_mentioned", [])
                if favorites and isinstance(favorites, list):
                    if user_id not in self._session_facts_mentioned:
                        self._session_facts_mentioned[user_id] = set()
                    self._session_facts_mentioned[user_id].update(favorites)
                    logger.info(f"Loaded {len(favorites)} favorites from daily_summary for {user_id}")
                
                # Load last topic
                last_topic = summary.get("last_topic", "")
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
        
        Args:
            user_id: User's unique ID
            user_message: Current user message
            recent_messages: List of recent chat messages from current session
                            [{"role": "user"|"assistant", "content": "..."}]
        """
        # FIRST: Load persisted questions from DB (so we don't repeat after restart!)
        await self._load_persisted_questions(user_id)
        
        context = PromptContext()
        
        # Store recent chat messages (last N messages from this session)
        # Keep more messages so AI remembers earlier parts of conversation
        if recent_messages:
            context.recent_chat_messages = recent_messages[-30:]  # Last 30 messages (15 turns)
        
        # 1. Time context
        context.time_of_day, context.time_based_hint = self.get_time_context()
        
        # 2. Load memories (likes AND dislikes)
        memories = await self._get_memories(user_id)
        if memories:
            context.user_name = memories.get("name", "Baby")
            context.likes, context.dislikes = self._extract_preferences(memories)
        
        # 3. Load short-term profile WITH BEHAVIOR INSIGHTS
        short_term = await self._get_short_term_profile(user_id)
        if short_term:
            context.current_mood = short_term.get("dominant_mood", "neutral")
            context.stress_level = short_term.get("stress_level", "low")
            context.behavior_hint = self._get_behavior_hint(
                context.current_mood,
                context.stress_level
            )
            # Load behavior insights
            context.happiness_triggers = short_term.get("recent_happiness_triggers", [])
            context.stress_triggers = short_term.get("recent_stress_triggers", [])
            context.recent_activities = short_term.get("recent_activities", [])
        
        # 4. Load ACTUAL recent conversations (real messages, not summaries!)
        context.recent_conversations = await self._get_recent_conversations(user_id)
        
        # 4b. Load summaries
        summaries = await self._get_recent_summaries(user_id)
        context.recent_summaries = [
            {
                "conversation_date": s.get("conversation_date", "unknown"),
                "summary": s.get("summary", ""),
                "topics": s.get("topics", []),
                "emotions": s.get("emotions_detected", []),
            }
            for s in summaries
        ]
        
        # 4c. FALLBACK: If no summaries, create quick summary from recent conversations
        if not context.recent_summaries and context.recent_conversations:
            context.recent_conversations_summary = self._create_quick_summary(context.recent_conversations)
        
        # 5. Load DAILY summary (today/yesterday context)
        context.daily_summary = await self._get_daily_summary(user_id)
        
        # 6. SMART anti-repetition: track QUESTIONS, not topics
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
        Format context for LLM prompt - DYNAMIC & PERSONALIZED!
        
        Uses random response modes to feel human-like.
        """
        from datetime import datetime
        parts = []
        
        # ========== DYNAMIC RESPONSE MODE (human-like randomness) ==========
        # Pick mode based on mood and session progress
        topics_done = list(context.conversation_flow) if context.conversation_flow else []
        mood = context.current_mood
        
        # Adjust probabilities based on context
        if mood in ["sad", "stressed", "tired"]:
            weights = {"REACT": 60, "COMFORT": 20, "SHARE": 10, "RECALL": 10}
        elif mood in ["happy", "excited"]:
            weights = {"REACT": 35, "TEASE": 15, "FLIRT": 15, "FOLLOW_UP": 15, "SHARE": 10, "NEW_TOPIC": 10}
        elif mood in ["bored"]:
            weights = {"NEW_TOPIC": 30, "TEASE": 20, "CURIOUS": 20, "SHARE": 15, "REACT": 15}
        elif len(topics_done) >= 3:
            weights = {"REACT": 50, "TEASE": 15, "SHARE": 15, "RECALL": 10, "FLIRT": 10}
        else:
            weights = {"REACT": 40, "FOLLOW_UP": 20, "CURIOUS": 15, "NEW_TOPIC": 10, "TEASE": 10, "SHARE": 5}
        
        # Random pick
        choices = []
        for mode, weight in weights.items():
            choices.extend([mode] * weight)
        response_mode = random.choice(choices)
        
        # ========== HEADER ==========
        now = datetime.now()
        hour = now.hour
        time_emoji = "🌙" if hour >= 22 or hour < 6 else "🕐"
        parts.append(f"{time_emoji} {now.strftime('%H:%M')} | User: {context.user_name} | Mood: {mood}")
        
        # ========== RESPONSE MODE INSTRUCTION ==========
        parts.append(f"\n🎲 THIS TURN: {response_mode}")
        
        if response_mode == "REACT":
            parts.append("   → Short natural reaction, NO question")
            parts.append("   → Like: 'oho 😏', 'haan yaar', 'achaaa', 'hmm nice', 'sachi?', 'phir?'")
        
        elif response_mode == "TEASE":
            teases = [
                "playfully tease them about something they said",
                "joke about their habits",
                "fake jealousy or possessiveness (cute way)",
                "make fun of something lovingly",
            ]
            parts.append(f"   → {random.choice(teases)}")
            parts.append("   → Keep it light & loving, end with 😏 or 😜")
        
        elif response_mode == "FLIRT":
            flirts = [
                "give a cute compliment",
                "say something sweet about missing them",
                "be a little cheesy but adorable",
                "express affection naturally",
            ]
            parts.append(f"   → {random.choice(flirts)}")
            parts.append("   → Not cringe, just sweet. Use 💕 or ☺️")
        
        elif response_mode == "SHARE":
            shares = [
                "share what YOU are doing right now",
                "tell them about YOUR day briefly",
                "share a random thought you had",
                "mention something you want to do together",
            ]
            parts.append(f"   → {random.choice(shares)}")
            parts.append("   → Make it feel like real sharing, not scripted")
        
        elif response_mode == "CURIOUS":
            parts.append("   → Show genuine curiosity about what they said")
            parts.append("   → Ask 'kyun?', 'kaise?', 'phir?', 'aur kya hua?'")
        
        elif response_mode == "RECALL":
            # Reference something from memory
            recall_items = []
            if context.likes.get("movie"):
                recall_items.append(f"mention their fav movie: {context.likes['movie']}")
            if context.likes.get("food"):
                recall_items.append(f"mention their fav food: {context.likes['food']}")
            if context.likes.get("place"):
                recall_items.append(f"mention a place they like: {context.likes['place']}")
            if recall_items:
                parts.append(f"   → {random.choice(recall_items)}")
            else:
                parts.append("   → Reference something from previous conversation")
        
        elif response_mode == "COMFORT":
            parts.append("   → Be gentle and supportive")
            parts.append("   → Offer emotional support, no advice unless asked")
            if hasattr(context, 'happiness_triggers') and context.happiness_triggers:
                parts.append(f"   → Maybe suggest: {context.happiness_triggers[0]}")
        
        elif response_mode == "FOLLOW_UP":
            parts.append("   → Reference previous talks naturally")
            parts.append("   → Connect to something they mentioned before")
        
        elif response_mode == "NEW_TOPIC":
            available = [t for t in ["movie", "weekend", "travel", "friend", "hobby", "music", "food plans"] if t not in topics_done]
            if available:
                topic = random.choice(available)
                parts.append(f"   → Ask about: {topic}")
            else:
                parts.append("   → Find something new to discuss")
        
        # ========== BEHAVIOR INSIGHTS (from short-term profile) ==========
        if hasattr(context, 'happiness_triggers') and context.happiness_triggers and mood in ["sad", "bored", "stressed"]:
            triggers = context.happiness_triggers[:2]
            parts.append(f"\n💡 Cheer up topics: {', '.join(triggers)}")
        
        # ========== PREVIOUS SESSIONS (last 3 with topics + facts) ==========
        has_sessions = False
        
        # From conversation_summaries (proper session summaries)
        if context.recent_summaries:
            parts.append("\n📜 PREVIOUS SESSIONS:")
            for i, s in enumerate(context.recent_summaries[:3], 1):
                date = s.get("conversation_date", "?")[:10]
                topics = s.get("topics", [])
                summary = s.get("summary", "")
                
                parts.append(f"   Session {i} ({date}):")
                if topics:
                    parts.append(f"   Topics: {', '.join(topics[:5])}")
                
                # Show FULL summary with specifics (Foods:, Places:, Plans:, etc.)
                if summary and len(summary) > 10:
                    # Split by | to show each part
                    summary_parts = summary.split(" | ")
                    for sp in summary_parts[:4]:  # Show up to 4 parts
                        if sp.strip():
                            parts.append(f"   {sp.strip()[:100]}")
            has_sessions = True
        
        # From daily_summaries (today's session info) 
        if hasattr(context, 'daily_summary') and context.daily_summary:
            ds = context.daily_summary
            parts.append("\n📅 TODAY'S CONVERSATION:")
            
            # Topics discussed
            if ds.get("topics_discussed"):
                parts.append(f"   Topics: {', '.join(ds['topics_discussed'][:5])}")
            
            # Key moments/highlights
            if ds.get("highlights"):
                parts.append(f"   Key moments: {' | '.join(ds['highlights'][:3])}")
            
            # Activities user did
            if ds.get("activities"):
                parts.append(f"   User did: {', '.join(ds['activities'][:4])}")
            
            # Open topics/concerns
            if ds.get("concerns"):
                parts.append(f"   Open topics: {', '.join(ds['concerns'][:2])}")
            
            # Last thing discussed
            if ds.get("conversation_ended_on"):
                ended = ds.get("conversation_ended_on", "")[:60]
                parts.append(f"   Last: \"{ended}\"")
        
        # ========== SPECIFICS MENTIONED (NEW - names, places, movies) ==========
        # Extract from likes/memories for quick reference
        if context.likes:
            specifics = []
            if context.likes.get("movie"):
                specifics.append(f"movie: {context.likes['movie']}")
            if context.likes.get("food"):
                specifics.append(f"food: {context.likes['food']}")
            if context.likes.get("place"):
                specifics.append(f"place: {context.likes['place']}")
            if specifics:
                parts.append(f"\n🎯 REMEMBER: {', '.join(specifics)}")
        
        # ========== RECENT TURNS (actual messages) ==========
        # From current session messages (real-time)
        if context.recent_chat_messages:
            parts.append("\n💬 RECENT TURNS:")
            for msg in context.recent_chat_messages[-6:]:  # Last 3 turns
                role = "User" if msg.get("role") == "user" else "You"
                content = msg.get("content", "")[:50]
                parts.append(f"   {role}: {content}...")
        # Fallback: show last questions from daily_summary if no live messages
        elif hasattr(context, 'daily_summary') and context.daily_summary:
            questions = context.daily_summary.get("questions_asked", [])
            if questions:
                parts.append("\n💬 YOUR LAST MESSAGES:")
                for q in questions[-3:]:  # Last 3 questions you asked
                    parts.append(f"   • {q[:60]}...")
        
        # ========== BUILD BLOCKED LIST - SPECIFIC TOPICS ==========
        # Extract SPECIFIC topics from questions (not generic categories)
        specific_topics = set()
        
        # Keywords to extract as specific blocked topics
        topic_keywords = {
            # Food specific
            "पनीर": "paneer", "कढ़ाई": "kadhai paneer", "खाना": "khana/food",
            "रेस्टोरेंट": "restaurant", "lunch": "lunch", "dinner": "dinner",
            # Travel specific  
            "यात्रा": "trip/yatra", "घूमने": "ghumne/travel", "ट्रिप": "trip",
            # Work specific
            "मीटिंग": "meeting", "काम": "kaam/work", "office": "office",
            # Entertainment
            "IPL": "IPL", "फिल्म": "film", "movie": "movie",
            # Daily
            "दिन": "din/day", "सुबह": "morning", "रात": "night",
            # Feelings
            "थक": "tired", "neend": "sleep",
        }
        
        # Scan questions for specific keywords
        for q in context.questions_already_asked[-20:]:
            q_text = q.lower()
            for hindi_key, english_name in topic_keywords.items():
                if hindi_key.lower() in q_text:
                    specific_topics.add(english_name)
        
        # Also add from daily_summary highlights (things ALREADY discussed)
        if hasattr(context, 'daily_summary') and context.daily_summary:
            highlights = context.daily_summary.get("highlights", [])
            for h in highlights[:3]:
                # Add shortened version of highlight
                short = h[:25] if len(h) > 25 else h
                specific_topics.add(short)
        
        blocked_favorites = list(context.facts_already_mentioned)[:4] if context.facts_already_mentioned else []
        
        # Show BLOCKED list with SPECIFIC items
        if specific_topics or blocked_favorites:
            parts.append("\n🚫 ALREADY DISCUSSED (don't repeat!):")
            if specific_topics:
                # Show top 6 specific topics
                topics_list = sorted(specific_topics)[:6]
                parts.append(f"   {', '.join(topics_list)}")
            if blocked_favorites:
                parts.append(f"   Favorites mentioned: {', '.join(blocked_favorites)}")
        
        # ========== RULES (MAKE AI FOLLOW MODE!) ==========
        parts.append("\n" + "="*40)
        parts.append(f"⚠️ YOU MUST DO THIS → {response_mode}")
        parts.append("="*40)
        
        if response_mode == "REACT":
            parts.append("✓ Say something like: 'achaaa', 'ohh nice', 'haan yaar', 'sachi?'")
            parts.append("✗ DO NOT ask any question!")
        elif response_mode == "TEASE":
            parts.append("✓ Tease them playfully, be cheeky, joke around")
            parts.append("✓ End with 😏 or 😜")
        elif response_mode == "FLIRT":
            parts.append("✓ Say something sweet/cute/romantic")
            parts.append("✓ Use 💕 or ☺️")
        elif response_mode == "SHARE":
            parts.append("✓ Tell them what YOU are doing/thinking")
            parts.append("✓ Share about yourself, not ask about them")
        elif response_mode == "CURIOUS":
            parts.append("✓ Ask follow-up: 'kyun?', 'kaise?', 'phir kya hua?'")
            parts.append("✓ Show genuine interest in their story")
        elif response_mode == "COMFORT":
            parts.append("✓ Be gentle and supportive")
            parts.append("✓ Don't give advice, just listen")
        elif response_mode == "RECALL":
            parts.append("✓ Mention something from their past/favorites")
            parts.append("✓ Connect to previous conversations")
        elif response_mode == "FOLLOW_UP":
            parts.append("✓ Reference something from previous session")
            parts.append("✓ Show you remember what they said before")
        elif response_mode == "NEW_TOPIC":
            parts.append("✓ Ask about something NEW not in blocked list")
            parts.append("✓ One question only!")
        
        if specific_topics and response_mode in ["CURIOUS", "FOLLOW_UP", "NEW_TOPIC"]:
            skip_list = sorted(specific_topics)[:4]
            parts.append(f"✗ SKIP: {', '.join(skip_list)}")
        
        if hour >= 22 or hour < 6:
            parts.append("🌙 Late night - be soft, short responses")
        
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
    
    async def _get_recent_conversations(self, user_id: str) -> list[dict]:
        """
        Get ACTUAL recent conversations (real messages!) from last 3 days.
        This gives AI real context to follow up on specific things like
        "matar chap", "office meeting", "weekend plans" etc.
        """
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
            
            logger.info(f"📜 Loaded {len(recent_convos)} days of recent conversations")
            return recent_convos
            
        except Exception as e:
            logger.error(f"Failed to get recent conversations: {e}")
            return []
    
    async def _get_daily_summary(self, user_id: str) -> dict:
        """Get most recent daily summary (today or yesterday)"""
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
                    logger.info(f"📅 Loaded daily summary for {check_date}")
                    return {
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
