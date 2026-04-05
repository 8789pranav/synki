"""
Smart Memory System - Layered Summaries for Perfect Context

Instead of passing raw chat history:
1. 24-HOUR SUMMARY (detailed) - What happened today
2. WEEKLY SUMMARY (high-level) - What happened this week
3. LONG-TERM FACTS - Permanent user facts

This gives the agent PERFECT context without token overload!
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class DailySummary:
    """24-hour conversation summary - DETAILED"""
    date: str  # YYYY-MM-DD
    
    # Mood tracking
    dominant_mood: str = "neutral"
    mood_changes: list[str] = field(default_factory=list)  # ["happy at morning", "stressed at evening"]
    
    # Topics discussed today
    topics_discussed: list[str] = field(default_factory=list)  # ["work", "food", "family"]
    
    # Questions ASKED today (to avoid repeating)
    questions_asked: list[str] = field(default_factory=list)  # ["kya khaya?", "office kaisa tha?"]
    
    # User activities mentioned
    activities: list[str] = field(default_factory=list)  # ["had meeting", "went for walk"]
    
    # Key moments/events
    highlights: list[str] = field(default_factory=list)  # ["user was stressed about deadline"]
    
    # Concerns/problems mentioned
    concerns: list[str] = field(default_factory=list)  # ["deadline tomorrow", "not sleeping well"]
    
    # Positive things
    positives: list[str] = field(default_factory=list)  # ["got promotion", "feeling better"]
    
    # Last conversation flow (what to continue)
    last_topic: str = ""
    conversation_ended_on: str = ""  # "user said goodnight", "user had to go for work"
    
    # Message count
    total_messages: int = 0
    user_messages: int = 0
    

@dataclass
class WeeklySummary:
    """7-day summary - HIGH LEVEL"""
    week_start: str  # YYYY-MM-DD
    week_end: str
    
    # Overall mood this week
    overall_mood: str = "neutral"
    mood_trend: str = "stable"  # "improving", "declining", "stable"
    
    # Major topics this week
    recurring_topics: list[str] = field(default_factory=list)
    
    # Key events this week
    key_events: list[str] = field(default_factory=list)  # ["promotion on Monday", "stressed about project"]
    
    # Patterns noticed
    patterns: list[str] = field(default_factory=list)  # ["usually stressed on weekdays", "happy on weekends"]
    
    # Conversation frequency
    total_conversations: int = 0
    total_messages: int = 0
    
    # What to remember for next week
    carry_forward: list[str] = field(default_factory=list)  # ["follow up on project", "ask about interview"]


class SmartMemoryService:
    """
    Manages layered summaries for perfect AI context.
    
    Usage:
        memory = SmartMemoryService(supabase)
        context = await memory.get_context_for_prompt(user_id)
        # Returns formatted string ready for injection
    """
    
    def __init__(self, supabase_client: Any = None, openai_client: Any = None):
        self._supabase = supabase_client
        self._openai = openai_client
        logger.info("SmartMemoryService initialized")
    
    async def get_context_for_prompt(self, user_id: str) -> str:
        """
        Get the PERFECT context for AI prompt.
        Returns a formatted string with:
        - Today's detailed summary
        - This week's high-level summary
        - Long-term facts
        """
        today_summary = await self.get_daily_summary(user_id)
        weekly_summary = await self.get_weekly_summary(user_id)
        facts = await self.get_long_term_facts(user_id)
        
        return self._format_context(today_summary, weekly_summary, facts)
    
    async def get_daily_summary(self, user_id: str, date: str = None) -> Optional[DailySummary]:
        """Get or generate today's summary"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Try to get from database
        if self._supabase:
            try:
                result = self._supabase.table('daily_summaries').select('*').eq('user_id', user_id).eq('date', date).execute()
                if result.data:
                    return self._parse_daily_summary(result.data[0])
            except Exception as e:
                logger.warning(f"Could not fetch daily summary: {e}")
        
        # Generate from today's conversations
        return await self._generate_daily_summary(user_id, date)
    
    async def get_weekly_summary(self, user_id: str) -> Optional[WeeklySummary]:
        """Get or generate this week's summary"""
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        
        # Try to get from database
        if self._supabase:
            try:
                result = self._supabase.table('weekly_summaries').select('*').eq('user_id', user_id).eq('week_start', week_start).execute()
                if result.data:
                    return self._parse_weekly_summary(result.data[0])
            except Exception as e:
                logger.warning(f"Could not fetch weekly summary: {e}")
        
        # Generate from daily summaries
        return await self._generate_weekly_summary(user_id, week_start)
    
    async def get_long_term_facts(self, user_id: str) -> list[str]:
        """Get permanent facts about user"""
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.table('memories').select('facts').eq('user_id', user_id).execute()
            if result.data and result.data[0].get('facts'):
                return result.data[0]['facts'][:10]  # Limit to 10 facts
        except Exception as e:
            logger.warning(f"Could not fetch facts: {e}")
        
        return []
    
    async def update_daily_summary(self, user_id: str, user_message: str, assistant_message: str, emotion: str = "neutral"):
        """Update today's summary with new conversation turn"""
        date = datetime.now().strftime("%Y-%m-%d")
        summary = await self.get_daily_summary(user_id, date) or DailySummary(date=date)
        
        # Update message counts
        summary.total_messages += 2
        summary.user_messages += 1
        
        # Extract topics from messages
        topics = self._extract_topics(user_message + " " + assistant_message)
        for topic in topics:
            if topic not in summary.topics_discussed:
                summary.topics_discussed.append(topic)
        
        # Track questions asked by assistant
        questions = self._extract_questions(assistant_message)
        for q in questions:
            if q not in summary.questions_asked:
                summary.questions_asked.append(q)
        
        # Update mood
        if emotion != "neutral":
            summary.mood_changes.append(f"{emotion} at {datetime.now().strftime('%H:%M')}")
            summary.dominant_mood = emotion
        
        # Extract activities from user message
        activities = self._extract_activities(user_message)
        for act in activities:
            if act not in summary.activities:
                summary.activities.append(act)
        
        # Update last topic
        if topics:
            summary.last_topic = topics[-1]
        
        # Save to database
        await self._save_daily_summary(user_id, summary)
        
        return summary
    
    async def _generate_daily_summary(self, user_id: str, date: str) -> DailySummary:
        """Generate daily summary from conversation history"""
        summary = DailySummary(date=date)
        
        if not self._supabase:
            return summary
        
        try:
            # Get today's conversations
            start_time = f"{date}T00:00:00"
            end_time = f"{date}T23:59:59"
            
            result = self._supabase.table('chat_history').select('*').eq('user_id', user_id).gte('created_at', start_time).lte('created_at', end_time).order('created_at', desc=False).execute()
            
            if not result.data:
                return summary
            
            # Process messages
            for msg in result.data:
                summary.total_messages += 1
                if msg['role'] == 'user':
                    summary.user_messages += 1
                    # Extract info from user messages
                    topics = self._extract_topics(msg['content'])
                    activities = self._extract_activities(msg['content'])
                    for t in topics:
                        if t not in summary.topics_discussed:
                            summary.topics_discussed.append(t)
                    for a in activities:
                        if a not in summary.activities:
                            summary.activities.append(a)
                else:
                    # Extract questions from assistant messages
                    questions = self._extract_questions(msg['content'])
                    for q in questions:
                        if q not in summary.questions_asked:
                            summary.questions_asked.append(q)
                
                # Track emotion
                if msg.get('emotion') and msg['emotion'] != 'neutral':
                    summary.mood_changes.append(f"{msg['emotion']} at {msg['created_at'][:16]}")
            
            # Set dominant mood from last few emotions
            if summary.mood_changes:
                last_mood = summary.mood_changes[-1].split(' at ')[0]
                summary.dominant_mood = last_mood
            
            # Set last topic
            if summary.topics_discussed:
                summary.last_topic = summary.topics_discussed[-1]
            
        except Exception as e:
            logger.warning(f"Error generating daily summary: {e}")
        
        return summary
    
    async def _generate_weekly_summary(self, user_id: str, week_start: str) -> WeeklySummary:
        """Generate weekly summary from daily summaries"""
        start_date = datetime.strptime(week_start, "%Y-%m-%d")
        end_date = start_date + timedelta(days=6)
        
        summary = WeeklySummary(
            week_start=week_start,
            week_end=end_date.strftime("%Y-%m-%d")
        )
        
        # Collect data from daily summaries
        all_topics = []
        all_moods = []
        
        for i in range(7):
            date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            daily = await self.get_daily_summary(user_id, date)
            if daily and daily.total_messages > 0:
                summary.total_conversations += 1
                summary.total_messages += daily.total_messages
                all_topics.extend(daily.topics_discussed)
                all_moods.append(daily.dominant_mood)
                
                # Add highlights as key events
                if daily.highlights:
                    for h in daily.highlights:
                        summary.key_events.append(f"{date}: {h}")
        
        # Find recurring topics
        topic_counts = {}
        for t in all_topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        summary.recurring_topics = [t for t, c in sorted(topic_counts.items(), key=lambda x: -x[1]) if c > 1][:5]
        
        # Determine mood trend
        if all_moods:
            mood_values = {"happy": 2, "excited": 2, "neutral": 1, "sad": 0, "stressed": 0, "angry": 0}
            mood_scores = [mood_values.get(m, 1) for m in all_moods]
            if len(mood_scores) >= 2:
                first_half = sum(mood_scores[:len(mood_scores)//2]) / max(len(mood_scores)//2, 1)
                second_half = sum(mood_scores[len(mood_scores)//2:]) / max(len(mood_scores) - len(mood_scores)//2, 1)
                if second_half > first_half + 0.3:
                    summary.mood_trend = "improving"
                elif second_half < first_half - 0.3:
                    summary.mood_trend = "declining"
            summary.overall_mood = all_moods[-1] if all_moods else "neutral"
        
        return summary
    
    async def _save_daily_summary(self, user_id: str, summary: DailySummary):
        """Save daily summary to database"""
        if not self._supabase:
            return
        
        try:
            data = {
                'user_id': user_id,
                'date': summary.date,
                'dominant_mood': summary.dominant_mood,
                'mood_changes': summary.mood_changes,
                'topics_discussed': summary.topics_discussed,
                'questions_asked': summary.questions_asked,
                'activities': summary.activities,
                'highlights': summary.highlights,
                'concerns': summary.concerns,
                'positives': summary.positives,
                'last_topic': summary.last_topic,
                'conversation_ended_on': summary.conversation_ended_on,
                'total_messages': summary.total_messages,
                'user_messages': summary.user_messages,
                'updated_at': datetime.now().isoformat()
            }
            
            self._supabase.table('daily_summaries').upsert(data, on_conflict='user_id,date').execute()
        except Exception as e:
            logger.warning(f"Could not save daily summary: {e}")
    
    async def finalize_daily_summary(self, user_id: str, conversation_text: str, last_message: str = ""):
        """
        Finalize daily summary at session end - similar to conversation summary.
        Generates LLM summary and updates highlights/concerns.
        """
        date = datetime.now().strftime("%Y-%m-%d")
        summary = await self.get_daily_summary(user_id, date) or DailySummary(date=date)
        
        # Set conversation ended on
        summary.conversation_ended_on = last_message[:100] if last_message else "session ended"
        
        # Generate highlights and concerns using LLM (if available)
        if self._openai and conversation_text:
            try:
                prompt = f"""Analyze this conversation and extract SPECIFIC details:

1. KEY_FACTS: Specific things mentioned (movie names, places, person names, dates, plans)
   Format: "watched: [movie name]", "going to: [place]", "friend: [name]", "plan: [detail]"
   
2. ACTIVITIES: What user did/is doing (with specifics)
   Format: "played badminton", "watched ZNMD", "meeting with team"

3. OPEN_TOPICS: Things to follow up on later
   Format: "wants to visit Kerala", "looking for new job"

Extract REAL NAMES and SPECIFICS, not generic descriptions!

Conversation:
{conversation_text[:2500]}

Format (each on new line):
KEY_FACTS: [fact1], [fact2], [fact3]
ACTIVITIES: [act1], [act2]
OPEN_TOPICS: [topic1], [topic2]"""

                response = await self._openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Extract SPECIFIC names, places, movies, people - not generic descriptions. Be precise."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=200,
                )
                
                result = response.choices[0].message.content.strip()
                
                # Parse KEY_FACTS → highlights
                if "KEY_FACTS:" in result:
                    facts_part = result.split("KEY_FACTS:")[1].split("ACTIVITIES:")[0] if "ACTIVITIES:" in result else result.split("KEY_FACTS:")[1].split("OPEN_TOPICS:")[0]
                    facts = [f.strip().strip("[]") for f in facts_part.split(",") if f.strip() and "none" not in f.lower()]
                    summary.highlights = facts[:4]  # Store up to 4 key facts
                
                # Parse ACTIVITIES
                if "ACTIVITIES:" in result:
                    acts_part = result.split("ACTIVITIES:")[1].split("OPEN_TOPICS:")[0] if "OPEN_TOPICS:" in result else result.split("ACTIVITIES:")[1]
                    activities = [a.strip().strip("[]") for a in acts_part.split(",") if a.strip() and "none" not in a.lower()]
                    # Merge with existing activities
                    for act in activities[:3]:
                        if act not in summary.activities:
                            summary.activities.append(act)
                
                # Parse OPEN_TOPICS → concerns
                if "OPEN_TOPICS:" in result:
                    topics_part = result.split("OPEN_TOPICS:")[1]
                    topics = [t.strip().strip("[]") for t in topics_part.split(",") if t.strip() and "none" not in t.lower()]
                    summary.concerns = topics[:3]
                
                logger.info(f"📅 Daily summary finalized: key_facts={summary.highlights}, activities={summary.activities}, open_topics={summary.concerns}")
                
            except Exception as e:
                logger.warning(f"Could not generate highlights/concerns: {e}")
        
        # Save final summary
        await self._save_daily_summary(user_id, summary)
        
        logger.info(f"✅ Daily summary finalized for {user_id} on {date}")
        return summary
    
    def _format_context(self, daily: Optional[DailySummary], weekly: Optional[WeeklySummary], facts: list[str]) -> str:
        """Format summaries into prompt-ready context"""
        parts = []
        
        # TODAY (Detailed)
        if daily and daily.total_messages > 0:
            parts.append("📅 TODAY'S CONTEXT:")
            parts.append(f"   Mood: {daily.dominant_mood}")
            
            if daily.activities:
                parts.append(f"   Activities: {', '.join(daily.activities[:5])}")
            
            if daily.topics_discussed:
                parts.append(f"   Topics discussed: {', '.join(daily.topics_discussed[:5])}")
            
            if daily.questions_asked:
                parts.append(f"   ⚠️ ALREADY ASKED (don't repeat): {', '.join(daily.questions_asked[-5:])}")
            
            if daily.concerns:
                parts.append(f"   Concerns: {', '.join(daily.concerns[:3])}")
            
            if daily.last_topic:
                parts.append(f"   Last topic: {daily.last_topic}")
            
            parts.append(f"   Messages today: {daily.total_messages}")
            parts.append("")
        
        # THIS WEEK (High-level)
        if weekly and weekly.total_conversations > 0:
            parts.append("📆 THIS WEEK:")
            parts.append(f"   Overall mood: {weekly.overall_mood} ({weekly.mood_trend})")
            
            if weekly.recurring_topics:
                parts.append(f"   Frequent topics: {', '.join(weekly.recurring_topics[:3])}")
            
            if weekly.key_events:
                parts.append(f"   Key events: {'; '.join(weekly.key_events[:3])}")
            
            if weekly.carry_forward:
                parts.append(f"   Follow up on: {', '.join(weekly.carry_forward[:3])}")
            
            parts.append("")
        
        # LONG-TERM FACTS
        if facts:
            parts.append("🧠 KNOWN FACTS:")
            for fact in facts[:5]:
                parts.append(f"   • {fact}")
            parts.append("")
        
        return "\n".join(parts) if parts else ""
    
    def _parse_daily_summary(self, data: dict) -> DailySummary:
        """Parse database row into DailySummary"""
        return DailySummary(
            date=data.get('date', ''),
            dominant_mood=data.get('dominant_mood', 'neutral'),
            mood_changes=data.get('mood_changes', []),
            topics_discussed=data.get('topics_discussed', []),
            questions_asked=data.get('questions_asked', []),
            activities=data.get('activities', []),
            highlights=data.get('highlights', []),
            concerns=data.get('concerns', []),
            positives=data.get('positives', []),
            last_topic=data.get('last_topic', ''),
            conversation_ended_on=data.get('conversation_ended_on', ''),
            total_messages=data.get('total_messages', 0),
            user_messages=data.get('user_messages', 0),
        )
    
    def _parse_weekly_summary(self, data: dict) -> WeeklySummary:
        """Parse database row into WeeklySummary"""
        return WeeklySummary(
            week_start=data.get('week_start', ''),
            week_end=data.get('week_end', ''),
            overall_mood=data.get('overall_mood', 'neutral'),
            mood_trend=data.get('mood_trend', 'stable'),
            recurring_topics=data.get('recurring_topics', []),
            key_events=data.get('key_events', []),
            patterns=data.get('patterns', []),
            total_conversations=data.get('total_conversations', 0),
            total_messages=data.get('total_messages', 0),
            carry_forward=data.get('carry_forward', []),
        )
    
    def _extract_topics(self, text: str) -> list[str]:
        """Extract topic categories from text"""
        text_lower = text.lower()
        topics = []
        
        topic_keywords = {
            "work": ["work", "office", "job", "kaam", "meeting", "boss", "project", "deadline"],
            "food": ["khana", "food", "eat", "lunch", "dinner", "breakfast", "chai", "coffee"],
            "health": ["tired", "sick", "doctor", "sleep", "gym", "exercise", "neend"],
            "family": ["mom", "dad", "family", "ghar", "parents", "brother", "sister"],
            "entertainment": ["movie", "song", "music", "netflix", "game", "show"],
            "travel": ["trip", "travel", "ghumne", "vacation", "plan"],
            "relationship": ["miss", "love", "pyaar", "alone", "lonely"],
            "stress": ["stress", "tension", "worried", "anxious", "problem"],
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in text_lower for kw in keywords):
                topics.append(topic)
        
        return topics
    
    def _extract_activities(self, text: str) -> list[str]:
        """Extract activities mentioned in text"""
        activities = []
        text_lower = text.lower()
        
        activity_patterns = [
            ("meeting", ["meeting", "call", "conference"]),
            ("eating", ["khaya", "eat", "lunch", "dinner", "breakfast"]),
            ("working", ["working", "kaam", "office"]),
            ("resting", ["rest", "relax", "aaraam"]),
            ("walking", ["walk", "gym", "exercise"]),
            ("watching", ["watching", "dekh", "movie", "show"]),
            ("talking", ["talking", "baat", "call"]),
        ]
        
        for activity, keywords in activity_patterns:
            if any(kw in text_lower for kw in keywords):
                activities.append(activity)
        
        return activities
    
    def _extract_questions(self, text: str) -> list[str]:
        """Extract questions from text"""
        questions = []
        
        # Split by ? and get question phrases
        if '?' in text:
            parts = text.split('?')
            for part in parts[:-1]:  # Last part is after final ?
                # Get last sentence before ?
                sentences = part.split('.')
                if sentences:
                    q = sentences[-1].strip()
                    if len(q) > 5 and len(q) < 100:
                        questions.append(q + '?')
        
        return questions[:3]  # Max 3 questions per message
