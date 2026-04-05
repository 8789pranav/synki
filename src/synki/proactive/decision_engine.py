"""
Decision Engine - Smart logic for when and how to proactively contact user

Factors considered:
1. Time since last conversation
2. Time of day (morning greeting, evening check-in, late night)
3. User's typical patterns (from short-term profile)
4. User's current mood/stress (don't bother if stressed)
5. Day of week (weekday vs weekend patterns)
6. Random natural variety (don't be predictable)
"""

import random
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class ContactType(Enum):
    """Type of proactive contact"""
    CALL = "call"           # Voice call (rings, user picks up)
    MESSAGE = "message"     # Text message (notification, user can reply)
    NONE = "none"           # Don't contact now


@dataclass
class ContactDecision:
    """Decision about whether and how to contact user"""
    should_contact: bool
    contact_type: ContactType
    reason: str
    message: Optional[str] = None
    priority: str = "normal"  # low, normal, high
    context: dict = None      # Extra context for the contact
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}


class DecisionEngine:
    """
    Decides when and how to proactively contact the user.
    
    Contact Rules:
    - Morning greeting (7-10 AM): 60% chance if not talked today
    - Lunch check-in (12-2 PM): 40% chance if not talked in 4+ hours
    - Evening call (6-9 PM): 70% chance if not talked in 6+ hours
    - Late night (10 PM-12 AM): 30% chance, gentle message
    - Random throughout day: 10% chance per hour
    
    Don't contact if:
    - User marked as busy
    - Less than 2 hours since last contact
    - User's stress level is high
    - Already contacted 3+ times today
    """
    
    # Minimum hours between contacts
    MIN_HOURS_BETWEEN_CONTACTS = 2
    MAX_CONTACTS_PER_DAY = 4
    
    # Time windows for proactive contact
    TIME_WINDOWS = {
        "morning_greeting": {"start": 7, "end": 10, "type": ContactType.MESSAGE, "chance": 0.6},
        "lunch_checkin": {"start": 12, "end": 14, "type": ContactType.MESSAGE, "chance": 0.4},
        "evening_call": {"start": 18, "end": 21, "type": ContactType.CALL, "chance": 0.7},
        "late_night": {"start": 22, "end": 24, "type": ContactType.MESSAGE, "chance": 0.3},
        "random": {"type": ContactType.MESSAGE, "chance": 0.1},  # Throughout day
    }
    
    def __init__(self, supabase_client=None):
        self._supabase = supabase_client
        logger.info("DecisionEngine initialized")
    
    async def should_contact(
        self,
        user_id: str,
        force_check: bool = False,
    ) -> ContactDecision:
        """
        Decide if we should proactively contact the user.
        
        Args:
            user_id: User's ID
            force_check: Bypass some checks (for testing)
            
        Returns:
            ContactDecision with should_contact, type, reason, message
        """
        now = datetime.now()
        hour = now.hour
        
        # 1. Get user data
        user_data = await self._get_user_data(user_id)
        
        # 2. Check if user is busy/unavailable
        if user_data.get("is_busy", False):
            return ContactDecision(
                should_contact=False,
                contact_type=ContactType.NONE,
                reason="User marked as busy"
            )
        
        # 3. Check last contact time
        last_contact = user_data.get("last_contact_at")
        if last_contact:
            hours_since = (now - last_contact).total_seconds() / 3600
            if hours_since < self.MIN_HOURS_BETWEEN_CONTACTS and not force_check:
                return ContactDecision(
                    should_contact=False,
                    contact_type=ContactType.NONE,
                    reason=f"Only {hours_since:.1f} hours since last contact"
                )
        else:
            hours_since = 24  # Never contacted before
        
        # 4. Check daily contact count
        contacts_today = user_data.get("contacts_today", 0)
        if contacts_today >= self.MAX_CONTACTS_PER_DAY and not force_check:
            return ContactDecision(
                should_contact=False,
                contact_type=ContactType.NONE,
                reason=f"Already contacted {contacts_today} times today"
            )
        
        # 5. Check user's stress level (don't bother if stressed)
        stress_level = user_data.get("stress_level", "low")
        if stress_level == "high":
            return ContactDecision(
                should_contact=False,
                contact_type=ContactType.NONE,
                reason="User stress level is high, giving space"
            )
        
        # 6. Determine current time window
        window = self._get_current_window(hour)
        
        # 7. Make decision based on window
        if window:
            window_config = self.TIME_WINDOWS[window]
            chance = window_config["chance"]
            
            # Increase chance if haven't talked in a while
            if hours_since > 8:
                chance = min(chance + 0.2, 0.9)
            if hours_since > 12:
                chance = min(chance + 0.3, 0.95)
            
            # Decrease chance if stressed (but not high stress - that's blocked above)
            if stress_level == "medium":
                chance *= 0.7
            
            # Roll the dice
            if random.random() < chance or force_check:
                contact_type = window_config["type"]
                
                # Evening calls are special - higher engagement
                if window == "evening_call" and hours_since > 6:
                    contact_type = ContactType.CALL
                
                return ContactDecision(
                    should_contact=True,
                    contact_type=contact_type,
                    reason=f"Time window: {window}, hours since contact: {hours_since:.1f}",
                    priority="high" if hours_since > 12 else "normal",
                    context={
                        "window": window,
                        "hours_since_contact": hours_since,
                        "user_mood": user_data.get("mood", "neutral"),
                        "is_first_today": contacts_today == 0,
                    }
                )
        
        # 8. Random chance throughout the day
        if hour >= 8 and hour <= 22:  # Only during reasonable hours
            if random.random() < self.TIME_WINDOWS["random"]["chance"]:
                return ContactDecision(
                    should_contact=True,
                    contact_type=ContactType.MESSAGE,
                    reason="Random check-in",
                    priority="low",
                    context={
                        "window": "random",
                        "hours_since_contact": hours_since,
                    }
                )
        
        # Default: Don't contact
        return ContactDecision(
            should_contact=False,
            contact_type=ContactType.NONE,
            reason="No appropriate time window / chance roll failed"
        )
    
    def _get_current_window(self, hour: int) -> Optional[str]:
        """Get the current time window name"""
        for name, config in self.TIME_WINDOWS.items():
            if name == "random":
                continue
            if config["start"] <= hour < config["end"]:
                return name
        return None
    
    async def _get_user_data(self, user_id: str) -> dict:
        """Get user data for decision making"""
        data = {
            "is_busy": False,
            "last_contact_at": None,
            "contacts_today": 0,
            "stress_level": "low",
            "mood": "neutral",
        }
        
        if not self._supabase:
            return data
        
        try:
            # Get last contact time from chat_history
            result = self._supabase.table("chat_history")\
                .select("created_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                last_msg = result.data[0]
                data["last_contact_at"] = datetime.fromisoformat(
                    last_msg["created_at"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
            
            # Count contacts today
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            result = self._supabase.table("proactive_contacts")\
                .select("id", count="exact")\
                .eq("user_id", user_id)\
                .gte("created_at", today_start.isoformat())\
                .execute()
            data["contacts_today"] = result.count or 0
            
            # Get stress level from short-term profile
            result = self._supabase.table("user_profiles_short_term")\
                .select("profile_data")\
                .eq("user_id", user_id)\
                .execute()
            
            if result.data:
                profile = result.data[0].get("profile_data", {})
                data["stress_level"] = profile.get("stress_level", "low")
                data["mood"] = profile.get("dominant_mood", "neutral")
                
        except Exception as e:
            logger.error(f"Failed to get user data: {e}")
        
        return data
    
    async def record_contact(self, user_id: str, contact_type: ContactType, message: str):
        """Record that we made a proactive contact"""
        if not self._supabase:
            return
        
        try:
            self._supabase.table("proactive_contacts").insert({
                "user_id": user_id,
                "contact_type": contact_type.value,
                "message": message,
                "created_at": datetime.now().isoformat(),
            }).execute()
            logger.info(f"Recorded proactive contact: {contact_type.value} to {user_id[:8]}...")
        except Exception as e:
            logger.error(f"Failed to record contact: {e}")
