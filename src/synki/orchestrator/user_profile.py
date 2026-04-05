"""
User Profile System

Comprehensive psychological profiling for personalized AI companion.

Two Profile Types:
1. SHORT-TERM PROFILE (Rolling 5-6 days)
   - Recent behavioral patterns
   - Current mood trends
   - Recent locations/activities
   - What's on user's mind lately

2. LONG-TERM PROFILE (Permanent deep analysis)
   - Personality traits
   - Emotional patterns
   - Triggers (what irritates/makes happy)
   - Dreams & goals
   - Family map
   - Life routines
   - Communication preferences
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class PersonalityTrait(str, Enum):
    """Big Five + additional traits"""
    INTROVERT = "introvert"
    EXTROVERT = "extrovert"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    EMOTIONAL = "emotional"
    LOGICAL = "logical"
    SPONTANEOUS = "spontaneous"
    PLANNER = "planner"
    OPTIMIST = "optimist"
    PESSIMIST = "pessimist"
    REALIST = "realist"
    EMPATHETIC = "empathetic"
    INDEPENDENT = "independent"
    SOCIAL = "social"
    RESERVED = "reserved"


class EmotionPattern(str, Enum):
    """Dominant emotional patterns"""
    USUALLY_CALM = "usually_calm"
    OFTEN_STRESSED = "often_stressed"
    GENERALLY_HAPPY = "generally_happy"
    FREQUENTLY_ANXIOUS = "frequently_anxious"
    MOOD_SWINGS = "mood_swings"
    EMOTIONALLY_STABLE = "emotionally_stable"
    SENSITIVE = "sensitive"
    RESILIENT = "resilient"


class CommunicationStyle(str, Enum):
    """How user prefers to communicate"""
    DIRECT = "direct"
    INDIRECT = "indirect"
    NEEDS_VALIDATION = "needs_validation"
    USES_HUMOR = "uses_humor"
    SERIOUS = "serious"
    CASUAL = "casual"
    DETAILED = "detailed"
    BRIEF = "brief"


class SupportPreference(str, Enum):
    """What user needs when upset"""
    WANTS_ADVICE = "wants_advice"
    JUST_LISTEN = "just_listen"
    NEEDS_DISTRACTION = "needs_distraction"
    WANTS_SOLUTIONS = "wants_solutions"
    NEEDS_VALIDATION = "needs_validation"
    PREFERS_SPACE = "prefers_space"
    NEEDS_COMFORT = "needs_comfort"


class TimeOfDay(str, Enum):
    """Time periods for pattern analysis"""
    EARLY_MORNING = "early_morning"   # 5-8 AM
    MORNING = "morning"               # 8-12 PM
    AFTERNOON = "afternoon"           # 12-5 PM
    EVENING = "evening"               # 5-9 PM
    NIGHT = "night"                   # 9 PM - 12 AM
    LATE_NIGHT = "late_night"         # 12-5 AM


class DayOfWeek(str, Enum):
    """Days for pattern analysis"""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


# =============================================================================
# SHORT-TERM PROFILE (Rolling 5-6 days)
# =============================================================================

@dataclass
class MoodEntry:
    """Single mood observation"""
    mood: str                    # happy, sad, stressed, excited, etc.
    intensity: float             # 0.0 to 1.0
    timestamp: datetime
    trigger: str | None = None   # What caused this mood
    context: str | None = None   # Conversation context


@dataclass
class LocationEntry:
    """Place user mentioned visiting"""
    place: str                   # "office", "that cafe", "gym"
    place_type: str              # work, leisure, fitness, social
    frequency: int = 1           # Times mentioned
    last_mentioned: datetime = field(default_factory=datetime.now)
    sentiment: str = "neutral"   # positive, negative, neutral


@dataclass
class ActivityEntry:
    """Recent activity or event"""
    activity: str                # "meeting", "workout", "movie"
    category: str                # work, fitness, entertainment, social
    timestamp: datetime
    sentiment: str = "neutral"
    energy_level: str = "medium" # low, medium, high


@dataclass 
class ConcernEntry:
    """Something on user's mind"""
    topic: str                   # "work deadline", "health", "relationship"
    severity: str                # low, medium, high
    first_mentioned: datetime
    times_mentioned: int = 1
    resolved: bool = False


@dataclass
class ShortTermProfile:
    """
    Rolling 5-6 day behavioral snapshot.
    Captures recent patterns and current state.
    """
    user_id: str
    
    # Recent moods (last 6 days)
    recent_moods: list[MoodEntry] = field(default_factory=list)
    dominant_mood: str = "neutral"
    mood_trend: str = "stable"  # improving, declining, stable, volatile
    
    # Recent locations
    recent_locations: list[LocationEntry] = field(default_factory=list)
    most_visited: str | None = None
    
    # Recent activities
    recent_activities: list[ActivityEntry] = field(default_factory=list)
    activity_level: str = "moderate"  # low, moderate, high
    
    # Energy patterns by time of day
    energy_by_time: dict[str, str] = field(default_factory=dict)
    # e.g., {"morning": "high", "afternoon": "low", "evening": "medium"}
    
    # Current concerns/what's on mind
    current_concerns: list[ConcernEntry] = field(default_factory=list)
    stress_level: str = "moderate"  # low, moderate, high
    
    # Recent triggers
    recent_happiness_triggers: list[str] = field(default_factory=list)
    recent_stress_triggers: list[str] = field(default_factory=list)
    
    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)
    data_points: int = 0  # Number of conversations analyzed
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "recent_moods": [
                {"mood": m.mood, "intensity": m.intensity, 
                 "timestamp": m.timestamp.isoformat(), "trigger": m.trigger}
                for m in self.recent_moods[-20:]  # Last 20 entries
            ],
            "dominant_mood": self.dominant_mood,
            "mood_trend": self.mood_trend,
            "recent_locations": [
                {"place": l.place, "type": l.place_type, "frequency": l.frequency}
                for l in self.recent_locations[-10:]
            ],
            "most_visited": self.most_visited,
            "recent_activities": [
                {"activity": a.activity, "category": a.category, "sentiment": a.sentiment}
                for a in self.recent_activities[-15:]
            ],
            "activity_level": self.activity_level,
            "energy_by_time": self.energy_by_time,
            "current_concerns": [
                {"topic": c.topic, "severity": c.severity, "times_mentioned": c.times_mentioned}
                for c in self.current_concerns if not c.resolved
            ],
            "stress_level": self.stress_level,
            "recent_happiness_triggers": self.recent_happiness_triggers[-5:],
            "recent_stress_triggers": self.recent_stress_triggers[-5:],
            "last_updated": self.last_updated.isoformat(),
            "data_points": self.data_points,
        }
    
    def get_summary(self, compact: bool = False) -> str:
        """Get human-readable summary for LLM context
        
        Args:
            compact: If True, return ultra-short version (~100 chars)
        """
        if compact:
            # Ultra-compact for casual chat
            parts = []
            if self.dominant_mood != "neutral":
                parts.append(f"Mood: {self.dominant_mood}")
            if self.stress_level == "high":
                parts.append("stressed")
            if self.current_concerns:
                parts.append(f"thinking about: {self.current_concerns[0].topic}")
            return " | ".join(parts) if parts else ""
        
        lines = []
        
        lines.append(f"📊 RECENT (Last 5-6 days):")
        lines.append(f"   Mood: {self.dominant_mood} ({self.mood_trend})")
        
        if self.stress_level != "moderate":
            lines.append(f"   Stress: {self.stress_level}")
        
        if self.current_concerns:
            concerns = [c.topic for c in self.current_concerns if not c.resolved][:2]
            if concerns:
                lines.append(f"   On mind: {', '.join(concerns)}")
        
        if self.recent_happiness_triggers:
            lines.append(f"   Happy from: {self.recent_happiness_triggers[0]}")
        
        return "\n".join(lines)


# =============================================================================
# LONG-TERM PROFILE (Permanent deep analysis)
# =============================================================================

@dataclass
class FamilyMember:
    """Family member information"""
    relation: str          # brother, sister, mom, dad, spouse, etc.
    name: str | None = None
    location: str | None = None
    age: int | None = None
    occupation: str | None = None
    relationship_quality: str = "good"  # close, good, distant, complicated
    last_mentioned: datetime | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class LifeGoal:
    """Dreams and aspirations"""
    goal: str              # "visit Switzerland", "start a business"
    category: str          # travel, career, personal, financial, relationship
    importance: str        # high, medium, low
    timeline: str | None = None  # "someday", "next year", "in 5 years"
    progress: str = "not_started"  # not_started, in_progress, achieved
    mentioned_count: int = 1
    first_mentioned: datetime = field(default_factory=datetime.now)


@dataclass
class RoutinePattern:
    """Daily/weekly routine patterns"""
    activity: str          # "morning coffee", "gym", "work"
    time_of_day: str       # morning, afternoon, evening, night
    days: list[str]        # ["monday", "wednesday", "friday"]
    frequency: str         # daily, weekly, occasionally
    importance: str        # ritual, habit, occasional
    sentiment: str         # enjoys, neutral, dislikes_but_does


@dataclass
class TriggerPattern:
    """What triggers specific emotions"""
    trigger: str           # "traffic", "work deadlines", "family calls"
    emotion: str           # happy, stressed, angry, sad, anxious
    intensity: str         # mild, moderate, strong
    frequency: str         # rare, occasional, frequent
    examples: list[str] = field(default_factory=list)
    coping_mechanism: str | None = None


@dataclass
class LongTermProfile:
    """
    Permanent psychological profile.
    Deep understanding built over time.
    """
    user_id: str
    
    # Basic info
    name: str | None = None
    preferred_name: str | None = None  # What they like to be called
    age: int | None = None
    gender: str | None = None
    location: str | None = None
    occupation: str | None = None
    
    # Personality analysis
    personality_traits: dict[str, float] = field(default_factory=dict)
    # e.g., {"introvert": 0.7, "analytical": 0.8, "emotional": 0.6}
    dominant_traits: list[str] = field(default_factory=list)
    personality_summary: str = ""
    
    # Emotional patterns
    emotional_patterns: dict[str, float] = field(default_factory=dict)
    # e.g., {"usually_calm": 0.6, "sometimes_anxious": 0.3}
    emotional_baseline: str = "neutral"
    emotional_range: str = "moderate"  # narrow, moderate, wide
    
    # Triggers
    irritation_triggers: list[TriggerPattern] = field(default_factory=list)
    happiness_triggers: list[TriggerPattern] = field(default_factory=list)
    stress_triggers: list[TriggerPattern] = field(default_factory=list)
    comfort_triggers: list[TriggerPattern] = field(default_factory=list)
    
    # Dreams & goals
    life_goals: list[LifeGoal] = field(default_factory=list)
    dream_destinations: list[str] = field(default_factory=list)
    career_aspirations: list[str] = field(default_factory=list)
    
    # Family & relationships
    family_members: list[FamilyMember] = field(default_factory=list)
    relationship_status: str | None = None
    social_circle_size: str = "moderate"  # small, moderate, large
    
    # Life routines
    routines: list[RoutinePattern] = field(default_factory=list)
    morning_person: bool | None = None
    weekend_preferences: list[str] = field(default_factory=list)
    favorite_places: list[str] = field(default_factory=list)  # Regular hangouts
    
    # Communication preferences
    communication_style: list[str] = field(default_factory=list)
    # e.g., ["direct", "uses_humor", "needs_validation"]
    preferred_support: list[str] = field(default_factory=list)
    # e.g., ["just_listen", "needs_comfort"]
    
    # Interests & preferences (deep)
    core_interests: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)  # What they value most
    pet_peeves: list[str] = field(default_factory=list)
    
    # Health & wellness
    health_notes: list[str] = field(default_factory=list)
    fitness_level: str | None = None
    sleep_pattern: str | None = None  # early_bird, night_owl, irregular
    
    # Metadata
    profile_created: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    confidence_score: float = 0.0  # How confident we are in this profile (0-1)
    total_conversations_analyzed: int = 0
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "basic": {
                "name": self.name,
                "preferred_name": self.preferred_name,
                "age": self.age,
                "gender": self.gender,
                "location": self.location,
                "occupation": self.occupation,
            },
            "personality": {
                "traits": self.personality_traits,
                "dominant": self.dominant_traits,
                "summary": self.personality_summary,
            },
            "emotional": {
                "patterns": self.emotional_patterns,
                "baseline": self.emotional_baseline,
                "range": self.emotional_range,
            },
            "triggers": {
                "irritation": [{"trigger": t.trigger, "intensity": t.intensity} 
                              for t in self.irritation_triggers],
                "happiness": [{"trigger": t.trigger, "intensity": t.intensity} 
                             for t in self.happiness_triggers],
                "stress": [{"trigger": t.trigger, "intensity": t.intensity} 
                          for t in self.stress_triggers],
            },
            "goals": {
                "life_goals": [{"goal": g.goal, "category": g.category, "importance": g.importance}
                              for g in self.life_goals],
                "dream_destinations": self.dream_destinations,
                "career": self.career_aspirations,
            },
            "family": [
                {"relation": f.relation, "name": f.name, "location": f.location}
                for f in self.family_members
            ],
            "routines": [
                {"activity": r.activity, "time": r.time_of_day, "frequency": r.frequency}
                for r in self.routines
            ],
            "communication": {
                "style": self.communication_style,
                "support_preference": self.preferred_support,
            },
            "interests": {
                "core": self.core_interests,
                "values": self.values,
                "pet_peeves": self.pet_peeves,
            },
            "metadata": {
                "created": self.profile_created.isoformat(),
                "updated": self.last_updated.isoformat(),
                "confidence": self.confidence_score,
                "conversations_analyzed": self.total_conversations_analyzed,
            },
        }
    
    def get_summary(self, compact: bool = False, topics: list[str] | None = None) -> str:
        """Get human-readable summary for LLM context
        
        Args:
            compact: If True, return ultra-short version (~150 chars)
            topics: If provided, only include relevant sections
        """
        if compact:
            # Ultra-compact for casual chat
            parts = []
            if self.preferred_name:
                parts.append(f"Name: {self.preferred_name}")
            if self.dominant_traits:
                parts.append(self.dominant_traits[0])
            if self.preferred_support:
                parts.append(f"needs: {self.preferred_support[0]}")
            return " | ".join(parts) if parts else ""
        
        lines = []
        lines.append(f"👤 PERSONALITY:")
        
        if self.preferred_name:
            lines.append(f"   Name: {self.preferred_name}")
        
        if self.personality_summary:
            lines.append(f"   {self.personality_summary[:80]}")
        elif self.dominant_traits:
            lines.append(f"   Traits: {', '.join(self.dominant_traits[:2])}")
        
        # Only include triggers if relevant or high confidence
        if self.confidence_score > 0.4:
            if self.irritation_triggers:
                lines.append(f"   Irritated by: {self.irritation_triggers[0].trigger}")
            if self.happiness_triggers:
                lines.append(f"   Happy from: {self.happiness_triggers[0].trigger}")
        
        if self.preferred_support:
            lines.append(f"   When upset: {self.preferred_support[0]}")
        
        return "\n".join(lines)


# =============================================================================
# PROFILE ANALYZER - Extracts insights from conversations
# =============================================================================

class ProfileAnalyzer:
    """
    Analyzes conversations to build and update user profiles.
    Uses LLM for deep psychological analysis.
    """
    
    SHORT_TERM_ANALYSIS_PROMPT = """You are a psychological analyst for a voice companion app.
Analyze this conversation snippet and extract SHORT-TERM behavioral data.

EXTRACT:
1. MOOD: What mood(s) did user express? (happy, sad, stressed, excited, anxious, tired, bored, angry, calm, etc.)
   - Include intensity (0.0-1.0) and any triggers
   
2. LOCATIONS: Any places mentioned (work, home, cafe, gym, etc.)
   - Classify type: work, leisure, fitness, social, home
   - Note sentiment about the place
   
3. ACTIVITIES: What did they do or plan to do?
   - Classify: work, fitness, entertainment, social, personal
   - Note energy level and sentiment
   
4. CONCERNS: What's on their mind? Any worries or things they're thinking about?
   - Rate severity: low, medium, high
   
5. TRIGGERS: What made them happy or stressed in this conversation?

6. ENERGY: Any indication of energy levels at different times?

Respond in JSON:
{{
    "moods": [
        {{"mood": "stressed", "intensity": 0.7, "trigger": "work deadline"}}
    ],
    "locations": [
        {{"place": "office", "type": "work", "sentiment": "negative"}}
    ],
    "activities": [
        {{"activity": "meeting", "category": "work", "sentiment": "stressful", "energy": "low"}}
    ],
    "concerns": [
        {{"topic": "project deadline", "severity": "high"}}
    ],
    "happiness_triggers": ["friend's call"],
    "stress_triggers": ["boss meeting"],
    "energy_notes": {{"time": "afternoon", "level": "low"}}
}}

If nothing relevant found, use empty arrays/objects.

CONVERSATION:
{conversation}"""

    LONG_TERM_ANALYSIS_PROMPT = """You are a deep psychological analyst building a permanent personality profile.
Analyze these conversation summaries from the past week and update the user's LONG-TERM profile.

CURRENT PROFILE:
{current_profile}

EXTRACT/UPDATE:
1. PERSONALITY TRAITS: (rate 0.0-1.0)
   - introvert vs extrovert
   - analytical vs emotional
   - spontaneous vs planner
   - optimist vs pessimist vs realist
   
2. EMOTIONAL PATTERNS:
   - What's their baseline emotional state?
   - How wide is their emotional range?
   - Are they emotionally stable or volatile?
   
3. TRIGGERS (what specifically causes emotions):
   - Irritation triggers (what annoys them)
   - Happiness triggers (what brings joy)
   - Stress triggers (what stresses them)
   - Comfort triggers (what calms them)
   
4. GOALS & DREAMS:
   - Life goals mentioned
   - Dream destinations
   - Career aspirations
   
5. FAMILY:
   - Family members mentioned (relation, name, location if known)
   - Relationship quality indicators
   
6. ROUTINES:
   - Daily/weekly patterns
   - Morning person or night owl?
   - Weekend preferences
   
7. COMMUNICATION STYLE:
   - Direct or indirect?
   - Uses humor?
   - Needs validation?
   - What kind of support do they prefer when upset?
   
8. VALUES & INTERESTS:
   - Core interests
   - What they value most
   - Pet peeves

Respond in JSON:
{{
    "personality_traits": {{
        "introvert": 0.7,
        "analytical": 0.8,
        "planner": 0.6
    }},
    "personality_summary": "A thoughtful introvert who values planning and logic",
    "emotional_baseline": "usually_calm",
    "emotional_range": "moderate",
    "irritation_triggers": [
        {{"trigger": "traffic jams", "intensity": "strong", "examples": ["mentioned hating traffic twice"]}}
    ],
    "happiness_triggers": [
        {{"trigger": "family calls", "intensity": "strong"}}
    ],
    "stress_triggers": [
        {{"trigger": "work deadlines", "intensity": "moderate"}}
    ],
    "life_goals": [
        {{"goal": "visit Switzerland", "category": "travel", "importance": "high"}}
    ],
    "family_members": [
        {{"relation": "brother", "name": "Rahul", "location": "Bangalore"}}
    ],
    "routines": [
        {{"activity": "morning coffee", "time": "morning", "frequency": "daily"}}
    ],
    "morning_person": false,
    "communication_style": ["direct", "uses_humor"],
    "preferred_support": ["just_listen", "needs_comfort"],
    "core_interests": ["technology", "travel", "fitness"],
    "values": ["family", "honesty", "growth"],
    "pet_peeves": ["lateness", "dishonesty"]
}}

WEEK'S CONVERSATIONS:
{conversations}"""

    def __init__(self, llm_client: Any = None):
        self._llm = llm_client
    
    async def analyze_short_term(
        self,
        conversation_text: str,
        current_profile: ShortTermProfile,
    ) -> dict:
        """Analyze a conversation for short-term profile updates"""
        if not self._llm:
            logger.warning("No LLM client for profile analysis")
            return {}
        
        try:
            prompt = self.SHORT_TERM_ANALYSIS_PROMPT.format(
                conversation=conversation_text
            )
            
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a psychological analyst. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Short-term analysis failed: {e}")
            return {}
    
    async def analyze_long_term(
        self,
        conversation_summaries: list[str],
        current_profile: LongTermProfile,
    ) -> dict:
        """Analyze week's conversations for long-term profile updates"""
        if not self._llm:
            logger.warning("No LLM client for profile analysis")
            return {}
        
        try:
            current_profile_json = json.dumps(current_profile.to_dict(), indent=2)
            conversations_text = "\n\n---\n\n".join(conversation_summaries)
            
            prompt = self.LONG_TERM_ANALYSIS_PROMPT.format(
                current_profile=current_profile_json,
                conversations=conversations_text,
            )
            
            response = await self._llm.chat.completions.create(
                model="gpt-4o",  # Use stronger model for deep analysis
                messages=[
                    {"role": "system", "content": "You are a psychological analyst building personality profiles. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            logger.error(f"Long-term analysis failed: {e}")
            return {}


# =============================================================================
# PROFILE SERVICE - Manages profiles with database
# =============================================================================

class UserProfileService:
    """
    Service for managing user profiles with database persistence.
    """
    
    def __init__(
        self,
        supabase_client: Any = None,
        llm_client: Any = None,
    ):
        self._supabase = supabase_client
        self._analyzer = ProfileAnalyzer(llm_client)
        
        # In-memory cache
        self._short_term_cache: dict[str, ShortTermProfile] = {}
        self._long_term_cache: dict[str, LongTermProfile] = {}
        
        logger.info("UserProfileService initialized")
    
    # =========================================================================
    # SHORT-TERM PROFILE
    # =========================================================================
    
    async def get_short_term_profile(self, user_id: str) -> ShortTermProfile:
        """Get or create short-term profile"""
        # Check cache
        if user_id in self._short_term_cache:
            profile = self._short_term_cache[user_id]
            # Refresh if older than 1 hour
            if (datetime.now() - profile.last_updated).seconds < 3600:
                return profile
        
        # Load from database
        profile = await self._load_short_term_from_db(user_id)
        if not profile:
            profile = ShortTermProfile(user_id=user_id)
        
        self._short_term_cache[user_id] = profile
        return profile
    
    async def update_short_term_from_conversation(
        self,
        user_id: str,
        conversation_text: str,
    ) -> ShortTermProfile:
        """Update short-term profile from a conversation"""
        print("\n" + "🔵"*30)
        print("📊 SHORT-TERM PROFILE ANALYSIS (Session End)")
        print("🔵"*30)
        print(f"   User ID: {user_id}")
        print(f"   Conversation Length: {len(conversation_text)} chars")
        
        profile = await self.get_short_term_profile(user_id)
        
        # Analyze conversation
        print("\n   📡 Calling LLM for short-term analysis...")
        analysis = await self._analyzer.analyze_short_term(
            conversation_text, profile
        )
        
        if not analysis:
            print("   ❌ No analysis returned")
            return profile
        
        print(f"\n   ✅ LLM Analysis Complete:")
        print(f"      Raw analysis: {json.dumps(analysis, indent=2)[:500]}...")
        
        # Update moods
        print(f"\n   📊 MOODS EXTRACTED → user_profiles_short_term:")
        for mood_data in analysis.get("moods", []):
            mood = MoodEntry(
                mood=mood_data.get("mood", "neutral"),
                intensity=mood_data.get("intensity", 0.5),
                timestamp=datetime.now(),
                trigger=mood_data.get("trigger"),
            )
            profile.recent_moods.append(mood)
            print(f"      - Mood: {mood.mood} | Intensity: {mood.intensity} | Trigger: {mood.trigger}")
        
        # Update locations
        print(f"\n   📍 LOCATIONS EXTRACTED → user_profiles_short_term:")
        for loc_data in analysis.get("locations", []):
            # Check if location already exists
            existing = next(
                (l for l in profile.recent_locations if l.place == loc_data.get("place")),
                None
            )
            if existing:
                existing.frequency += 1
                existing.last_mentioned = datetime.now()
                print(f"      - Location: {existing.place} (updated, freq={existing.frequency})")
            else:
                loc = LocationEntry(
                    place=loc_data.get("place", "unknown"),
                    place_type=loc_data.get("type", "other"),
                    sentiment=loc_data.get("sentiment", "neutral"),
                )
                profile.recent_locations.append(loc)
                print(f"      - Location: {loc.place} | Type: {loc.place_type} | Sentiment: {loc.sentiment}")
        
        # Update activities
        print(f"\n   🏃 ACTIVITIES EXTRACTED → user_profiles_short_term:")
        for act_data in analysis.get("activities", []):
            activity = ActivityEntry(
                activity=act_data.get("activity", "unknown"),
                category=act_data.get("category", "other"),
                timestamp=datetime.now(),
                sentiment=act_data.get("sentiment", "neutral"),
                energy_level=act_data.get("energy", "medium"),
            )
            profile.recent_activities.append(activity)
            print(f"      - Activity: {activity.activity} | Category: {activity.category} | Energy: {activity.energy_level}")
        
        # Update concerns
        print(f"\n   😟 CONCERNS EXTRACTED → user_profiles_short_term:")
        for concern_data in analysis.get("concerns", []):
            existing = next(
                (c for c in profile.current_concerns if c.topic == concern_data.get("topic")),
                None
            )
            if existing:
                existing.times_mentioned += 1
                print(f"      - Concern: {existing.topic} (mentioned {existing.times_mentioned}x)")
            else:
                concern = ConcernEntry(
                    topic=concern_data.get("topic", "unknown"),
                    severity=concern_data.get("severity", "medium"),
                    first_mentioned=datetime.now(),
                )
                profile.current_concerns.append(concern)
                print(f"      - Concern: {concern.topic} | Severity: {concern.severity}")
        
        # Update triggers
        print(f"\n   😊 HAPPINESS TRIGGERS → user_profiles_short_term:")
        for trigger in analysis.get("happiness_triggers", []):
            print(f"      - {trigger}")
        profile.recent_happiness_triggers.extend(analysis.get("happiness_triggers", []))
        
        print(f"\n   😰 STRESS TRIGGERS → user_profiles_short_term:")
        for trigger in analysis.get("stress_triggers", []):
            print(f"      - {trigger}")
        profile.recent_stress_triggers.extend(analysis.get("stress_triggers", []))
        
        # Update energy notes
        energy_notes = analysis.get("energy_notes", {})
        if energy_notes.get("time") and energy_notes.get("level"):
            profile.energy_by_time[energy_notes["time"]] = energy_notes["level"]
            print(f"\n   ⚡ ENERGY → {energy_notes['time']}: {energy_notes['level']}")
        
        # Calculate derived fields
        profile = self._calculate_short_term_derived(profile)
        
        # Update metadata
        profile.last_updated = datetime.now()
        profile.data_points += 1
        
        # Prune old data (keep only last 6 days)
        profile = self._prune_old_short_term_data(profile)
        
        # Save to database
        await self._save_short_term_to_db(profile)
        
        # Update cache
        self._short_term_cache[user_id] = profile
        
        print(f"\n   💾 SAVED TO DATABASE: user_profiles_short_term")
        print(f"      Total Moods: {len(profile.recent_moods)}")
        print(f"      Total Locations: {len(profile.recent_locations)}")
        print(f"      Total Concerns: {len(profile.current_concerns)}")
        print(f"      Dominant Mood: {profile.dominant_mood}")
        print(f"      Stress Level: {profile.stress_level}")
        print("🔵"*30 + "\n")
        
        logger.info(
            "short_term_profile_updated",
            user_id=user_id,
            moods=len(profile.recent_moods),
            locations=len(profile.recent_locations),
        )
        
        return profile
    
    def _calculate_short_term_derived(self, profile: ShortTermProfile) -> ShortTermProfile:
        """Calculate derived fields from raw data"""
        # Dominant mood (most frequent in last 24 hours)
        recent_moods = [
            m for m in profile.recent_moods
            if (datetime.now() - m.timestamp).days < 1
        ]
        if recent_moods:
            mood_counts: dict[str, float] = {}
            for m in recent_moods:
                mood_counts[m.mood] = mood_counts.get(m.mood, 0) + m.intensity
            profile.dominant_mood = max(mood_counts, key=mood_counts.get)
        
        # Mood trend
        if len(profile.recent_moods) >= 4:
            early = profile.recent_moods[:len(profile.recent_moods)//2]
            late = profile.recent_moods[len(profile.recent_moods)//2:]
            
            positive_moods = {"happy", "excited", "calm", "content"}
            early_positive = sum(1 for m in early if m.mood in positive_moods) / len(early)
            late_positive = sum(1 for m in late if m.mood in positive_moods) / len(late)
            
            if late_positive - early_positive > 0.2:
                profile.mood_trend = "improving"
            elif early_positive - late_positive > 0.2:
                profile.mood_trend = "declining"
            else:
                profile.mood_trend = "stable"
        
        # Most visited location
        if profile.recent_locations:
            profile.most_visited = max(
                profile.recent_locations,
                key=lambda l: l.frequency
            ).place
        
        # Activity level
        recent_activities = [
            a for a in profile.recent_activities
            if (datetime.now() - a.timestamp).days < 3
        ]
        if len(recent_activities) > 10:
            profile.activity_level = "high"
        elif len(recent_activities) > 5:
            profile.activity_level = "moderate"
        else:
            profile.activity_level = "low"
        
        # Stress level
        high_severity_concerns = [c for c in profile.current_concerns if c.severity == "high"]
        stress_moods = [m for m in recent_moods if m.mood in {"stressed", "anxious", "worried"}]
        
        if len(high_severity_concerns) >= 2 or len(stress_moods) >= 3:
            profile.stress_level = "high"
        elif len(high_severity_concerns) >= 1 or len(stress_moods) >= 1:
            profile.stress_level = "moderate"
        else:
            profile.stress_level = "low"
        
        return profile
    
    def _prune_old_short_term_data(self, profile: ShortTermProfile) -> ShortTermProfile:
        """Remove data older than 6 days"""
        cutoff = datetime.now() - timedelta(days=6)
        
        profile.recent_moods = [m for m in profile.recent_moods if m.timestamp > cutoff]
        profile.recent_activities = [a for a in profile.recent_activities if a.timestamp > cutoff]
        profile.recent_locations = [
            l for l in profile.recent_locations 
            if l.last_mentioned > cutoff
        ]
        
        # Keep only last 5 triggers
        profile.recent_happiness_triggers = profile.recent_happiness_triggers[-5:]
        profile.recent_stress_triggers = profile.recent_stress_triggers[-5:]
        
        return profile
    
    # =========================================================================
    # LONG-TERM PROFILE
    # =========================================================================
    
    async def get_long_term_profile(self, user_id: str) -> LongTermProfile:
        """Get or create long-term profile"""
        # Check cache
        if user_id in self._long_term_cache:
            return self._long_term_cache[user_id]
        
        # Load from database
        profile = await self._load_long_term_from_db(user_id)
        if not profile:
            profile = LongTermProfile(user_id=user_id)
        
        self._long_term_cache[user_id] = profile
        return profile
    
    async def run_weekly_analysis(
        self,
        user_id: str,
        conversation_summaries: list[str],
    ) -> LongTermProfile:
        """Run weekly deep analysis to update long-term profile"""
        profile = await self.get_long_term_profile(user_id)
        
        # Analyze conversations
        analysis = await self._analyzer.analyze_long_term(
            conversation_summaries, profile
        )
        
        if not analysis:
            return profile
        
        # Update personality traits
        new_traits = analysis.get("personality_traits", {})
        for trait, score in new_traits.items():
            # Weighted average with existing (favor new slightly)
            old_score = profile.personality_traits.get(trait, 0.5)
            profile.personality_traits[trait] = (old_score * 0.4 + score * 0.6)
        
        # Update dominant traits
        if profile.personality_traits:
            sorted_traits = sorted(
                profile.personality_traits.items(),
                key=lambda x: x[1],
                reverse=True
            )
            profile.dominant_traits = [t[0] for t in sorted_traits[:3] if t[1] > 0.5]
        
        # Update personality summary
        if analysis.get("personality_summary"):
            profile.personality_summary = analysis["personality_summary"]
        
        # Update emotional patterns
        if analysis.get("emotional_baseline"):
            profile.emotional_baseline = analysis["emotional_baseline"]
        if analysis.get("emotional_range"):
            profile.emotional_range = analysis["emotional_range"]
        
        # Update triggers
        for trigger_data in analysis.get("irritation_triggers", []):
            self._update_trigger_list(
                profile.irritation_triggers, trigger_data, "irritation"
            )
        for trigger_data in analysis.get("happiness_triggers", []):
            self._update_trigger_list(
                profile.happiness_triggers, trigger_data, "happiness"
            )
        for trigger_data in analysis.get("stress_triggers", []):
            self._update_trigger_list(
                profile.stress_triggers, trigger_data, "stress"
            )
        
        # Update life goals
        for goal_data in analysis.get("life_goals", []):
            existing = next(
                (g for g in profile.life_goals if g.goal == goal_data.get("goal")),
                None
            )
            if existing:
                existing.mentioned_count += 1
            else:
                goal = LifeGoal(
                    goal=goal_data.get("goal", ""),
                    category=goal_data.get("category", "personal"),
                    importance=goal_data.get("importance", "medium"),
                )
                profile.life_goals.append(goal)
        
        # Update family members
        for family_data in analysis.get("family_members", []):
            existing = next(
                (f for f in profile.family_members 
                 if f.relation == family_data.get("relation") and 
                    (f.name == family_data.get("name") or not f.name)),
                None
            )
            if existing:
                if family_data.get("name"):
                    existing.name = family_data["name"]
                if family_data.get("location"):
                    existing.location = family_data["location"]
                existing.last_mentioned = datetime.now()
            else:
                member = FamilyMember(
                    relation=family_data.get("relation", ""),
                    name=family_data.get("name"),
                    location=family_data.get("location"),
                )
                profile.family_members.append(member)
        
        # Update routines
        for routine_data in analysis.get("routines", []):
            existing = next(
                (r for r in profile.routines if r.activity == routine_data.get("activity")),
                None
            )
            if not existing:
                routine = RoutinePattern(
                    activity=routine_data.get("activity", ""),
                    time_of_day=routine_data.get("time", "morning"),
                    days=[],
                    frequency=routine_data.get("frequency", "occasionally"),
                    importance="habit",
                    sentiment="neutral",
                )
                profile.routines.append(routine)
        
        # Update other fields
        if analysis.get("morning_person") is not None:
            profile.morning_person = analysis["morning_person"]
        
        if analysis.get("communication_style"):
            profile.communication_style = analysis["communication_style"]
        
        if analysis.get("preferred_support"):
            profile.preferred_support = analysis["preferred_support"]
        
        if analysis.get("core_interests"):
            # Merge with existing
            profile.core_interests = list(set(
                profile.core_interests + analysis["core_interests"]
            ))[:10]
        
        if analysis.get("values"):
            profile.values = list(set(
                profile.values + analysis["values"]
            ))[:5]
        
        if analysis.get("pet_peeves"):
            profile.pet_peeves = list(set(
                profile.pet_peeves + analysis["pet_peeves"]
            ))[:5]
        
        # Update metadata
        profile.last_updated = datetime.now()
        profile.total_conversations_analyzed += len(conversation_summaries)
        profile.confidence_score = min(
            0.95,
            0.3 + (profile.total_conversations_analyzed * 0.01)
        )
        
        # Save to database
        await self._save_long_term_to_db(profile)
        
        # Update cache
        self._long_term_cache[user_id] = profile
        
        logger.info(
            "long_term_profile_updated",
            user_id=user_id,
            confidence=profile.confidence_score,
            traits=len(profile.personality_traits),
        )
        
        return profile
    
    def _update_trigger_list(
        self,
        trigger_list: list[TriggerPattern],
        trigger_data: dict,
        emotion: str,
    ):
        """Update or add trigger to list"""
        existing = next(
            (t for t in trigger_list if t.trigger == trigger_data.get("trigger")),
            None
        )
        if existing:
            # Update frequency
            existing.frequency = "frequent"
            if trigger_data.get("examples"):
                existing.examples.extend(trigger_data["examples"])
                existing.examples = existing.examples[-5:]  # Keep last 5
        else:
            trigger = TriggerPattern(
                trigger=trigger_data.get("trigger", ""),
                emotion=emotion,
                intensity=trigger_data.get("intensity", "moderate"),
                frequency="occasional",
                examples=trigger_data.get("examples", []),
            )
            trigger_list.append(trigger)
    
    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================
    
    async def _load_short_term_from_db(self, user_id: str) -> ShortTermProfile | None:
        """Load short-term profile from database"""
        if not self._supabase:
            return None
        
        try:
            result = self._supabase.table("user_profiles_short_term").select("*").eq(
                "user_id", user_id
            ).execute()
            
            if result.data:
                data = result.data[0]
                profile = ShortTermProfile(user_id=user_id)
                
                # Parse JSON fields
                profile_data = data.get("profile_data", {})
                if isinstance(profile_data, str):
                    profile_data = json.loads(profile_data)
                
                profile.dominant_mood = profile_data.get("dominant_mood", "neutral")
                profile.mood_trend = profile_data.get("mood_trend", "stable")
                profile.stress_level = profile_data.get("stress_level", "moderate")
                profile.activity_level = profile_data.get("activity_level", "moderate")
                profile.most_visited = profile_data.get("most_visited")
                profile.energy_by_time = profile_data.get("energy_by_time", {})
                profile.recent_happiness_triggers = profile_data.get("recent_happiness_triggers", [])
                profile.recent_stress_triggers = profile_data.get("recent_stress_triggers", [])
                profile.data_points = profile_data.get("data_points", 0)
                
                return profile
                
        except Exception as e:
            logger.error(f"Failed to load short-term profile: {e}")
        
        return None
    
    async def _save_short_term_to_db(self, profile: ShortTermProfile):
        """Save short-term profile to database"""
        if not self._supabase:
            return
        
        try:
            data = {
                "user_id": profile.user_id,
                "profile_data": profile.to_dict(),
                "updated_at": datetime.now().isoformat(),
            }
            
            self._supabase.table("user_profiles_short_term").upsert(
                data, on_conflict="user_id"
            ).execute()
            
        except Exception as e:
            logger.error(f"Failed to save short-term profile: {e}")
    
    async def _load_long_term_from_db(self, user_id: str) -> LongTermProfile | None:
        """Load long-term profile from database"""
        if not self._supabase:
            return None
        
        try:
            result = self._supabase.table("user_profiles_long_term").select("*").eq(
                "user_id", user_id
            ).execute()
            
            if result.data:
                data = result.data[0]
                profile = LongTermProfile(user_id=user_id)
                
                # Parse JSON fields
                profile_data = data.get("profile_data", {})
                if isinstance(profile_data, str):
                    profile_data = json.loads(profile_data)
                
                # Basic info
                basic = profile_data.get("basic", {})
                profile.name = basic.get("name")
                profile.preferred_name = basic.get("preferred_name")
                profile.age = basic.get("age")
                profile.location = basic.get("location")
                profile.occupation = basic.get("occupation")
                
                # Personality
                personality = profile_data.get("personality", {})
                profile.personality_traits = personality.get("traits", {})
                profile.dominant_traits = personality.get("dominant", [])
                profile.personality_summary = personality.get("summary", "")
                
                # Emotional
                emotional = profile_data.get("emotional", {})
                profile.emotional_baseline = emotional.get("baseline", "neutral")
                profile.emotional_range = emotional.get("range", "moderate")
                
                # Communication
                comm = profile_data.get("communication", {})
                profile.communication_style = comm.get("style", [])
                profile.preferred_support = comm.get("support_preference", [])
                
                # Interests
                interests = profile_data.get("interests", {})
                profile.core_interests = interests.get("core", [])
                profile.values = interests.get("values", [])
                profile.pet_peeves = interests.get("pet_peeves", [])
                
                # Metadata
                metadata = profile_data.get("metadata", {})
                profile.confidence_score = metadata.get("confidence", 0)
                profile.total_conversations_analyzed = metadata.get("conversations_analyzed", 0)
                
                return profile
                
        except Exception as e:
            logger.error(f"Failed to load long-term profile: {e}")
        
        return None
    
    async def _save_long_term_to_db(self, profile: LongTermProfile):
        """Save long-term profile to database"""
        if not self._supabase:
            return
        
        try:
            data = {
                "user_id": profile.user_id,
                "profile_data": profile.to_dict(),
                "updated_at": datetime.now().isoformat(),
            }
            
            self._supabase.table("user_profiles_long_term").upsert(
                data, on_conflict="user_id"
            ).execute()
            
        except Exception as e:
            logger.error(f"Failed to save long-term profile: {e}")
    
    # =========================================================================
    # CONTEXT GENERATION
    # =========================================================================
    
    async def get_recent_session_summaries(
        self,
        user_id: str,
        limit: int = 2,
    ) -> list[dict]:
        """Get last N session summaries for context injection"""
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.table("conversation_summaries").select(
                "summary, conversation_date, topics"
            ).eq(
                "user_id", user_id
            ).order(
                "conversation_date", desc=True
            ).limit(limit).execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to get session summaries: {e}")
            return []
    
    async def get_profile_context(
        self, 
        user_id: str,
        user_text: str = "",
        compact: bool = True,
        include_session_history: bool = True,
    ) -> str:
        """Get combined profile context for LLM injection
        
        Args:
            user_id: User ID
            user_text: Current user message (for relevance filtering)
            compact: Use compact summaries (default True for efficiency)
            include_session_history: Include last 2 session summaries
        
        Returns:
            Context string, typically 200-500 chars
        """
        short_term = await self.get_short_term_profile(user_id)
        long_term = await self.get_long_term_profile(user_id)
        
        # Decide if we need full context or compact
        needs_full = False
        emotional_keywords = ["stressed", "sad", "anxious", "worried", "upset", "angry",
                            "tired", "exhausted", "happy", "excited", "family", "relationship"]
        if user_text:
            text_lower = user_text.lower()
            needs_full = any(kw in text_lower for kw in emotional_keywords)
        
        if short_term.stress_level == "high":
            needs_full = True
        
        use_compact = compact and not needs_full
        
        context_parts = []
        
        # 1. Previous session summaries (MOST VALUABLE for continuity!)
        if include_session_history:
            recent_sessions = await self.get_recent_session_summaries(user_id, limit=2)
            if recent_sessions:
                session_context = "📝 RECENT CONVERSATIONS:\n"
                for i, sess in enumerate(recent_sessions):
                    date = sess.get("conversation_date", "")
                    summary = sess.get("summary", "")[:150]  # Truncate if too long
                    if summary:
                        session_context += f"   {date}: {summary}\n"
                context_parts.append(session_context.strip())
        
        # 2. Long-term context (only if we have confidence)
        if long_term.confidence_score > 0.3:
            long_summary = long_term.get_summary(compact=use_compact)
            if long_summary:
                context_parts.append(long_summary)
        
        # 3. Short-term context (only if we have data)
        if short_term.data_points > 0:
            short_summary = short_term.get_summary(compact=use_compact)
            if short_summary:
                context_parts.append(short_summary)
        
        return "\n".join(context_parts) if context_parts else ""
