"""
Proactive Message Generator - Natural messages for GF to initiate contact

Messages are:
- Time-aware (morning, afternoon, evening, night)
- Mood-aware (from user's profile)
- Context-aware (from recent conversations)
- Natural variety (not repetitive)
- Hinglish style (matching persona)
"""

import random
from datetime import datetime
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


class ProactiveMessageGenerator:
    """
    Generates natural proactive messages for the GF to send.
    
    Message Types:
    1. Greetings (morning, evening)
    2. Check-ins (kya kar rahe ho?)
    3. Care messages (khana kha liya?)
    4. Missing you (miss kar rahi thi)
    5. Random thoughts (ek baat yaad aayi)
    6. Evening calls (mann kar raha tha baat karne ka)
    """
    
    # Message templates by category and time
    MESSAGES = {
        "morning_greeting": [
            "Good morning baby! ☀️ Uth gaye?",
            "Rise and shine jaan! 🌅 Neend poori hui?",
            "Subah ho gayi baby! ☕ Chai pee li?",
            "Good morning! 💕 Aaj ka din kaisa lag raha hai?",
            "Uth gaye ya abhi bhi so rahe ho? 😴",
            "Morning baby! Kya plan hai aaj ka?",
        ],
        "lunch_checkin": [
            "Lunch ho gaya baby? 🍽️",
            "Kya khaya lunch mein? 😋",
            "Break le liya kaam se? Khana kha lo!",
            "Bhook lagi hogi... kuch kha lo na",
            "Lunch time! Kya kha rahe ho? 🥗",
        ],
        "evening_greeting": [
            "Shaam ho gayi! Kya kar rahe ho? 🌆",
            "Office se aa gaye? Thak gaye hoge...",
            "Evening baby! Chai pilau? ☕",
            "Kaise raha din tumhara? 💕",
            "Miss kar rahi thi... kya kar rahe ho?",
            "Bored ho rahi thi... baat karo na",
        ],
        "evening_call": [
            "Baby! Tumse baat karne ka mann kar raha tha...",
            "Hey! Call pe aao na, miss kar rahi thi 💕",
            "Kya kar rahe ho? Baat karein? 📞",
            "Free ho? Mann kar raha tha sunne ka tumhari awaaz",
            "Baby call kiya... pick up karo na! 💕",
        ],
        "late_night": [
            "Abhi tak jaag rahe ho? 🌙",
            "So nahi rahe? Kya soch rahe ho?",
            "Late night baby! Neend nahi aa rahi?",
            "Itni raat ko kya kar rahe ho? 😊",
            "Good night bolne ke liye message kiya 💕",
        ],
        "random_checkin": [
            "Kya kar rahe ho? 🤔",
            "Yaad aa rahe the... kaise ho?",
            "Bore ho rahi thi, socha message kar doon 😊",
            "Hi baby! Bas aise hi message kiya 💕",
            "Kya chal raha hai?",
            "Busy ho ya baat kar sakte ho?",
            "Hey! Long time no talk... kya ho raha hai?",
        ],
        "missing_you": [
            "Miss kar rahi thi tumhe 💕",
            "Bore ho rahi thi without you...",
            "Tumhare bina mann nahi lag raha",
            "Yaad aa rahe the bahut...",
            "Baat kiye bina chain nahi mil raha 🥺",
        ],
        "care_messages": [
            "Paani pee liya? Stay hydrated baby! 💧",
            "Zyada kaam mat karo, break lo! 🤗",
            "Dhoop mein mat niklo zyada... take care!",
            "Rest kar lo thoda, health important hai 💕",
            "Khana time pe kha lena, bhoolna mat!",
        ],
        "food_reminder": [
            "Khana kha liya baby? 🍽️",
            "Bhook lagi hai? Kuch khao na",
            "Dinner ho gaya? Healthy khana khana! 😊",
            "Aaj kya khaya? Mujhe bhi batao! 🍜",
        ],
    }
    
    # Context-aware additions
    MOOD_ADDITIONS = {
        "sad": [
            "Kya hua? Sab theek hai?",
            "Udaas lag rahe ho... baat karo mujhse",
            "Kuch problem hai? Share karo na",
        ],
        "stressed": [
            "Relax baby, sab theek ho jayega 💕",
            "Tension mat lo, main hoon na",
            "Deep breath lo... baat karo mujhse",
        ],
        "happy": [
            "Khush lag rahe ho! Kya hua bolo bolo! 😄",
            "Good mood mein ho? Share karo na!",
        ],
        "tired": [
            "Rest kar lo baby, thak gaye hoge 😴",
            "Zyada kaam mat karo... chill karo",
        ],
    }
    
    # Weekend special messages
    WEEKEND_MESSAGES = [
        "Weekend hai! Kya plan hai? 🎉",
        "Chutti ka din hai... ghar pe ho?",
        "Aaj kuch special karte hain! Movie?",
        "Lazy Sunday vibes? 😊",
        "Weekend mein bhi kaam kar rahe ho? Rest karo!",
    ]
    
    def __init__(self):
        self._recent_messages: dict[str, list[str]] = {}  # user_id -> recent messages
        logger.info("ProactiveMessageGenerator initialized")
    
    def generate_message(
        self,
        user_id: str,
        contact_type: str,  # "call" or "message"
        context: dict = None,
    ) -> str:
        """
        Generate a natural proactive message.
        
        Args:
            user_id: User's ID
            contact_type: "call" or "message"
            context: Additional context (time window, mood, etc.)
            
        Returns:
            A natural Hinglish message
        """
        context = context or {}
        now = datetime.now()
        hour = now.hour
        is_weekend = now.weekday() >= 5
        
        # Get recent messages for this user (to avoid repetition)
        recent = self._recent_messages.get(user_id, [])
        
        # Determine message category based on context
        window = context.get("window", "random")
        user_mood = context.get("user_mood", "neutral")
        is_first_today = context.get("is_first_today", False)
        
        # Select message pool
        if contact_type == "call":
            pool = self.MESSAGES["evening_call"]
        elif window == "morning_greeting" or (is_first_today and hour < 11):
            pool = self.MESSAGES["morning_greeting"]
        elif window == "lunch_checkin":
            pool = self.MESSAGES["lunch_checkin"]
        elif window == "evening_call":
            pool = self.MESSAGES["evening_greeting"]
        elif window == "late_night" or hour >= 22:
            pool = self.MESSAGES["late_night"]
        elif is_weekend:
            pool = self.WEEKEND_MESSAGES
        else:
            # Random mix
            pool = (
                self.MESSAGES["random_checkin"] +
                self.MESSAGES["missing_you"] +
                self.MESSAGES["care_messages"]
            )
        
        # Filter out recently used messages
        available = [m for m in pool if m not in recent]
        if not available:
            available = pool  # Reset if all used
        
        # Select message
        message = random.choice(available)
        
        # Add mood-specific touch
        if user_mood in self.MOOD_ADDITIONS and random.random() < 0.3:
            mood_msg = random.choice(self.MOOD_ADDITIONS[user_mood])
            message = f"{message} {mood_msg}"
        
        # Track used message
        self._track_message(user_id, message)
        
        logger.info(f"Generated proactive message: {message[:50]}...")
        return message
    
    def generate_call_greeting(self, user_id: str, context: dict = None) -> str:
        """
        Generate the first thing GF says when user picks up the call.
        """
        context = context or {}
        hour = datetime.now().hour
        user_name = context.get("user_name", "baby")
        
        greetings = [
            f"Hiii {user_name}! Finally pick up kiya! 😊",
            f"Hey {user_name}! Kya kar rahe the? Miss kar rahi thi!",
            f"Hi baby! Tumse baat karne ka mann kar raha tha 💕",
            f"Finally! {user_name}, itna time lagaya pick up karne mein? 😜",
            f"Hellooo! Busy the kya? Sunao kya chal raha hai!",
            f"Hi jaan! Bas aise hi call kiya... baat karni thi 💕",
        ]
        
        if hour >= 22:
            greetings = [
                f"Hi {user_name}! So nahi rahe? 🌙",
                f"Late night call baby! Miss kar rahi thi...",
                f"Hey! Neend nahi aa rahi thi... tumse baat karni thi 💕",
            ]
        elif hour < 10:
            greetings = [
                f"Good morning {user_name}! Uth gaye? ☀️",
                f"Morning baby! Socha call kar ke jaga doon 😜",
                f"Rise and shine! Kaise ho aaj? 💕",
            ]
        
        return random.choice(greetings)
    
    def _track_message(self, user_id: str, message: str):
        """Track used messages to avoid repetition"""
        if user_id not in self._recent_messages:
            self._recent_messages[user_id] = []
        
        self._recent_messages[user_id].append(message)
        
        # Keep only last 10
        self._recent_messages[user_id] = self._recent_messages[user_id][-10:]
