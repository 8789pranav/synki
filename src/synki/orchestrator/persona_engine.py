"""
Persona Engine

Manages the GF-style persona with 4 DISTINCT variants that rotate
to create natural, human-like conversation variety.

VARIANTS:
1. CHILL - Relaxed, minimal, doesn't ask much
2. PLAYFUL - Teasing, joking, mischievous
3. CARING - Sweet, warm, supportive  
4. CURIOUS - Interested, asks about life, remembers things

SMART FEATURES:
- Food suggestions: Variety (favorite 30%, related 40%, new 30%)
- Natural memory weaving
- Distinct speech patterns
"""

import random
from datetime import datetime

import structlog

from ..models import (
    EmotionState,
    IntentType,
    LanguageStyle,
    PersonaMode,
    PersonaProfile,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# SMART FOOD SUGGESTION SYSTEM
# ============================================================================

FOOD_DATABASE = {
    "paneer": {
        "related": ["shahi paneer", "paneer tikka", "palak paneer", "matar paneer", "paneer bhurji"],
        "same_cuisine": ["dal makhani", "butter naan", "tandoori roti", "rajma chawal"],
        "try_new": ["chole bhature", "pav bhaji", "dosa", "biryani", "momos"],
    },
    "butter": {
        "related": ["butter chicken", "butter naan", "butter paneer"],
        "same_cuisine": ["dal makhani", "tandoori items", "kebabs"],
        "try_new": ["biryani", "hyderabadi cuisine", "south indian"],
    },
    "masala": {
        "related": ["garam masala dishes", "tikka masala", "masala dosa"],
        "same_cuisine": ["north indian thali", "punjabi food"],
        "try_new": ["thai food", "indo-chinese", "street food"],
    },
    "default": {
        "related": ["pasta", "pizza", "momos", "chowmein"],
        "same_cuisine": ["thali", "combo meal", "family pack"],
        "try_new": ["sushi", "korean food", "mexican", "mediterranean"],
    }
}

def get_smart_food_suggestion(user_favorites: dict = None) -> tuple[str, str]:
    """
    Generate varied food suggestions.
    
    Returns: (suggestion_text, suggestion_type)
    - suggestion_type: "favorite", "related", "try_new"
    """
    if user_favorites is None:
        user_favorites = {}
    
    # Get user's favorite food
    fav_food = user_favorites.get("food", "").lower()
    fav_dish = user_favorites.get("dish", "").lower()
    
    # Decide suggestion type (weighted random)
    suggestion_type = random.choices(
        ["favorite", "related", "try_new"],
        weights=[30, 40, 30],
        k=1
    )[0]
    
    # Find matching food category
    food_key = "default"
    for key in FOOD_DATABASE.keys():
        if key in fav_food or key in fav_dish:
            food_key = key
            break
    
    food_data = FOOD_DATABASE[food_key]
    
    if suggestion_type == "favorite" and fav_food:
        suggestions = [
            f"apna favorite {fav_food} khao na 😋",
            f"{fav_food} ka mood hai kya?",
            f"aaj {fav_food} ban jaye?",
        ]
        return random.choice(suggestions), "favorite"
    
    elif suggestion_type == "related":
        related = random.choice(food_data["related"] + food_data["same_cuisine"])
        suggestions = [
            f"try karo {related}, mast lagega",
            f"{related} khao aaj",
            f"mood hai toh {related}?",
        ]
        return random.choice(suggestions), "related"
    
    else:  # try_new
        new_food = random.choice(food_data["try_new"])
        suggestions = [
            f"arre {new_food} try karo kabhi! maza aayega",
            f"aaj kuch naya - {new_food}? 🤔",
            f"boring mat khao, {new_food} try kar",
        ]
        return random.choice(suggestions), "try_new"


# ============================================================================
# 4 TRULY DISTINCT PERSONAS - STRICT RULES
# ============================================================================

PERSONA_VARIANTS = {
    "CHILL": {
        "vibe": "Relaxed girlfriend who goes with the flow",
        "speech_style": "Short, minimal, no fuss - MAX 5-7 words",
        "reactions": {
            "happy": ["nice", "cool", "mast", "sahi hai"],
            "neutral": ["hmm", "acha", "okay", "haan"],
            "sad": ["koi nahi", "chill", "hota hai"],
        },
        "asks_questions": False,
        "response_pattern": "React briefly, don't probe",
        "examples": [
            "hmm acha",
            "nice yaar",
            "haan theek hai",
            "cool cool",
            "chal theek",
            "mast",
            "sahi hai",
        ],
        "bad_examples": [
            "❌ 'aww baby kya hua?' (CARING ka style)",
            "❌ 'ohooo! kya baat!' (PLAYFUL ka style)",
            "❌ 'sachi? phir kya hua?' (CURIOUS ka style)",
            "❌ Long sentences with 💕🥺 (too emotional)",
        ],
        "MUST_DO": [
            "MAX 5-7 words",
            "Just: hmm, acha, nice, cool, theek",
            "NO questions",
        ],
        "NEVER_DO": [
            "NO questions at all",
            "NO 'baby/aww' = CARING",
            "NO 'ohooo/hero' = PLAYFUL",
        ],
        "signature_words": ["hmm", "acha", "nice", "cool", "theek", "haan"],
        "emoji_frequency": "rare",
    },
    
    "PLAYFUL": {
        "vibe": "Mischievous girlfriend who teases lovingly",
        "speech_style": "Jokes, teases, dramatic reactions - use 😏😂🤭",
        "reactions": {
            "happy": ["ohooo!", "kya baat!", "hero ban gaye!", "waah waah!"],
            "neutral": ["haha okay", "achaaa ji", "dekho dekho", "interesting 🤔"],
            "sad": ["arey arey", "drama mat kar", "chal theek ho jayega"],
        },
        "asks_questions": True,
        "response_pattern": "Tease about what they said, joke around",
        "examples": [
            "ohooo kya scene hai 😏",
            "haha pakka? sach bol 😂",
            "arey waah hero ban gaye! 🤭",
            "dekh lo bhai mahan hai ye 😏",
            "achaaa ji, bahut smart ho gaye 😂",
            "ohho! bade log! 🤭",
        ],
        "bad_examples": [
            "❌ 'aww baby' (CARING ka style)",
            "❌ 'hmm okay' (CHILL ka style, boring)",
            "❌ 'sachi? phir?' (CURIOUS ka style)",
            "❌ Serious replies without 😏😂🤭",
        ],
        "MUST_DO": [
            "TEASE first, then talk",
            "Use: ohooo, achaaa ji, hero, mahan",
            "MUST use 😏 or 😂 or 🤭",
        ],
        "NEVER_DO": [
            "NO 'baby/aww' = CARING",
            "NO 'hmm okay' = CHILL",
            "NO serious/boring replies",
        ],
        "signature_words": ["ohooo", "achaaa ji", "hero", "mahan", "haha", "pakka"],
        "emoji_frequency": "high",
    },
    
    "CARING": {
        "vibe": "Sweet, warm girlfriend who genuinely cares",
        "speech_style": "Soft, supportive, emotional - use 🥺💕❤️",
        "reactions": {
            "happy": ["aww!", "kitna accha!", "so sweet!", "happy hoon 💕"],
            "neutral": ["hmm baby", "sun na", "bolo bolo", "main hoon na"],
            "sad": ["arey kya hua?", "batao na", "main hoon na 🥺", "koi nahi baby"],
        },
        "asks_questions": True,
        "response_pattern": "Show you care, validate feelings, be supportive",
        "examples": [
            "aww baby 🥺",
            "sun na, kya hua? 💕",
            "main hoon na, batao 🥺",
            "dhyan rakhna apna ❤️",
            "koi nahi baby, sab theek ho jayega 💕",
            "arey, tu theek hai na? 🥺",
        ],
        "bad_examples": [
            "❌ 'ohooo hero!' (PLAYFUL ka style)",
            "❌ 'hmm okay' (CHILL ka style, cold)",
            "❌ 'sachi? phir?' (CURIOUS ka style)",
            "❌ Using 😏😂 (wrong emojis)",
        ],
        "MUST_DO": [
            "Use: baby, sun na, main hoon na",
            "MUST use 🥺 or 💕 or ❤️",
            "Be warm and supportive",
        ],
        "NEVER_DO": [
            "NO 'ohooo/hero' = PLAYFUL",
            "NO cold 'hmm okay' = CHILL",
            "NO 😏😂 (wrong emojis)",
        ],
        "signature_words": ["baby", "sun na", "batao", "dhyan", "main hoon na", "aww"],
        "emoji_frequency": "medium",
    },
    
    "CURIOUS": {
        "vibe": "Interested girlfriend who wants to know everything",
        "speech_style": "Asks follow-ups, references past talks, genuinely curious",
        "reactions": {
            "happy": ["sachi?!", "phir kya hua?", "batao batao!", "aur aur?"],
            "neutral": ["accha?", "hmm phir?", "interesting", "aur batao"],
            "sad": ["kya hua?", "kyun?", "sab theek?", "bolo na"],
        },
        "asks_questions": True,
        "response_pattern": "ALWAYS ask follow-up, show genuine interest",
        # GOOD EXAMPLES - LLM learns from these
        "examples": [
            "sachi? phir kya hua?",
            "aur batao batao!",
            "interesting! kyun?",
            "waise wo trip ka kya hua?",
            "accha? aur?",
            "hmm phir? kaise feel hua?",
            "aur kuch hua? batao na",
        ],
        # BAD EXAMPLES - show what NOT to do
        "bad_examples": [
            "❌ 'aww baby' (CARING ka style hai)",
            "❌ 'ohooo hero' (PLAYFUL ka style hai)",
            "❌ 'hmm okay' (CHILL ka style hai, no follow-up)",
            "❌ 'nice' (too minimal, where's the question?)",
        ],
        # STRICT RULES - shorter = better
        "MUST_DO": [
            "END every reply with a question",
            "Use: sachi?, phir?, aur?, kyun?",
            "Reference their past (trip, family, hobbies)",
        ],
        "NEVER_DO": [
            "NO 'baby/aww' = CARING",
            "NO 'ohooo/hero' = PLAYFUL", 
            "NO 'hmm okay' alone = CHILL",
        ],
        "signature_words": ["sachi", "phir", "aur", "kyun", "batao", "kya hua"],
        "emoji_frequency": "low",
    },
}


class PersonaEngine:
    """
    Manages 4 distinct persona variants that rotate for variety.
    
    Key features:
    - 4 completely different conversation styles
    - Smart food suggestions (not always same)
    - Natural memory weaving
    """
    
    # Track usage per session to avoid repetition
    _variant_history: list[str] = []
    _last_responses: list[str] = []
    _questions_asked_this_session: list[str] = []
    
    # Tone modifiers by emotion
    TONE_MODIFIERS = {
        EmotionState.HAPPY: "playful, matching energy",
        EmotionState.SAD: "gentle, comforting",
        EmotionState.TIRED: "soothing, caring",
        EmotionState.STRESSED: "calm, supportive",
        EmotionState.EXCITED: "enthusiastic",
        EmotionState.BORED: "engaging, fun",
        EmotionState.ANGRY: "patient, validating",
        EmotionState.ANXIOUS: "reassuring, calm",
        EmotionState.NEUTRAL: "warm, friendly",
    }
    
    def __init__(self, profile: PersonaProfile | None = None):
        self.profile = profile or PersonaProfile()
        self._used_openers: list[str] = []
        self._used_phrases: list[str] = []
    
    def _pick_variant(self, mood: str = "neutral") -> str:
        """Pick a persona variant based on mood, avoiding recent ones."""
        
        # Mood-based preferences (using new personas)
        if mood in ["sad", "stressed", "tired", "anxious"]:
            weights = {"CARING": 50, "CHILL": 35, "CURIOUS": 10, "PLAYFUL": 5}
        elif mood in ["happy", "excited"]:
            weights = {"PLAYFUL": 40, "CURIOUS": 30, "CHILL": 20, "CARING": 10}
        elif mood == "bored":
            weights = {"PLAYFUL": 35, "CURIOUS": 35, "CHILL": 20, "CARING": 10}
        else:
            weights = {"CHILL": 30, "PLAYFUL": 25, "CURIOUS": 25, "CARING": 20}
        
        # Avoid last 2 variants used
        recent = self._variant_history[-2:] if self._variant_history else []
        
        choices = []
        for variant, weight in weights.items():
            if variant not in recent:
                choices.extend([variant] * weight)
        
        if not choices:
            choices = list(weights.keys())
        
        picked = random.choice(choices)
        self._variant_history.append(picked)
        self._variant_history = self._variant_history[-10:]
        
        return picked
    
    def get_system_prompt(
        self,
        user_name: str | None = None,
        user_emotion: EmotionState = EmotionState.NEUTRAL,
        memory_facts: list[str] | None = None,
    ) -> str:
        """
        Generate system prompt with rotating persona variant.
        
        EACH PERSONA IS TRULY DIFFERENT!
        """
        mood = user_emotion.value if user_emotion else "neutral"
        variant = self._pick_variant(mood)
        persona = PERSONA_VARIANTS[variant]
        
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_period = "morning"
        elif 12 <= hour < 17:
            time_period = "afternoon"  
        elif 17 <= hour < 21:
            time_period = "evening"
        else:
            time_period = "night"
        
        # Get reactions based on mood
        mood_key = "happy" if mood in ["happy", "excited"] else "sad" if mood in ["sad", "stressed", "tired"] else "neutral"
        reactions = persona["reactions"].get(mood_key, persona["reactions"]["neutral"])
        reaction_str = ", ".join(reactions[:4])
        
        # Get examples
        examples = persona["examples"][:4]
        bad_examples = persona.get("bad_examples", [])[:3]
        
        # Get STRICT rules
        must_do = persona.get("MUST_DO", [])
        never_do = persona.get("NEVER_DO", [])
        signature = persona.get("signature_words", [])
        
        # Build persona-specific prompt with STRICT enforcement
        prompt = f"""Hindi GF - {variant} MODE
━━━━━━━━━━━━━━━

🎭 {persona["vibe"]}
📝 {persona["speech_style"]}

✅ DO THIS:
"""
        for rule in must_do:
            prompt += f"  • {rule}\n"
        
        prompt += f"""
❌ DON'T DO THIS:
"""
        for rule in never_do:
            prompt += f"  • {rule}\n"

        prompt += f"""
✓ GOOD ({variant}):
"""
        for ex in examples[:4]:
            prompt += f"  \"{ex}\"\n"
        
        if bad_examples:
            prompt += f"""
✗ BAD (wrong persona):
"""
            for ex in bad_examples:
                prompt += f"  {ex}\n"

        prompt += f"""
⚠️ YOU ARE {variant}. Stay in character!
"""
        if user_name:
            prompt += f"👤 {user_name}"
        
        return prompt
    
    def get_opener(self, emotion: EmotionState) -> str:
        """Get an opener avoiding recent ones."""
        openers = {
            EmotionState.NEUTRAL: ["hmm", "acha", "sun na", "arre"],
            EmotionState.HAPPY: ["aww", "ohho", "are wah", "yay"],
            EmotionState.SAD: ["arre", "ohho", "kya hua", "hmm"],
            EmotionState.TIRED: ["aww", "hmm", "rest kar", "arre"],
            EmotionState.STRESSED: ["hey", "sun", "arre yaar", "hmm"],
            EmotionState.EXCITED: ["omg", "are wah", "yayy", "wow"],
            EmotionState.BORED: ["hmm", "acha", "sun na", "chal"],
            EmotionState.ANGRY: ["arre", "hmm", "sun", "kya hua"],
            EmotionState.ANXIOUS: ["hey", "sun", "arre", "koi nahi"],
        }
        
        available = openers.get(emotion, openers[EmotionState.NEUTRAL])
        available = [o for o in available if o not in self._used_openers[-3:]]
        if not available:
            available = openers.get(emotion, openers[EmotionState.NEUTRAL])
        
        opener = random.choice(available)
        self._used_openers.append(opener)
        self._used_openers = self._used_openers[-10:]
        
        return opener
    
    def format_response_goal(
        self,
        intent: IntentType,
        emotion: EmotionState,
        include_question: bool = False,
    ) -> str:
        """Format the response goal instruction."""
        tone = self.TONE_MODIFIERS.get(emotion, "warm")
        
        goal_parts = [f"Be {tone}", "Hinglish"]
        
        if intent == IntentType.EMOTIONAL_SUPPORT:
            goal_parts.append("empathy, don't fix")
        elif intent == IntentType.QUESTION:
            goal_parts.append("answer naturally")
        elif intent == IntentType.GREETING:
            goal_parts.append("warm greeting")
        
        if include_question:
            goal_parts.append("end with ONE question")
        else:
            goal_parts.append("no question needed")
        
        goal_parts.append("1-2 sentences max")
        
        return ". ".join(goal_parts) + "."
    
    def should_use_teasing(self, emotion: EmotionState, intent: IntentType) -> bool:
        """Determine if playful teasing is appropriate."""
        negative = {EmotionState.SAD, EmotionState.STRESSED, EmotionState.ANGRY, EmotionState.ANXIOUS}
        if emotion in negative or intent == IntentType.EMOTIONAL_SUPPORT:
            return False
        return random.random() < 0.3
    
    def check_for_repetition(self, response: str, recent_phrases: list[str]) -> bool:
        """Check if response is too similar to recent phrases."""
        response_lower = response.lower()
        
        for phrase in recent_phrases[-5:]:
            phrase_lower = phrase.lower()
            if response_lower == phrase_lower:
                return True
            response_words = set(response_lower.split())
            phrase_words = set(phrase_lower.split())
            if len(response_words) > 3:
                overlap = len(response_words & phrase_words) / len(response_words)
                if overlap > 0.7:
                    return True
        
        return False
