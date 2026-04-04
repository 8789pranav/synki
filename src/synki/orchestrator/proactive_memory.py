"""
Proactive Memory Prompter

Detects when important information is mentioned but incomplete,
and generates follow-up questions to gather missing details.

Examples:
- "I need to take my medicine" → Ask "Kaun si medicine baby?"
- "My birthday is coming" → Ask "Kab hai birthday?"
- "I have a meeting" → Ask "Kitne baje hai meeting?"
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum

import structlog

from .layered_memory import (
    Entity,
    EntityType,
    MemoryFact,
    MemoryCategory,
)

logger = structlog.get_logger(__name__)


class MemoryTopic(str, Enum):
    """Topics that warrant proactive memory collection."""
    MEDICINE = "medicine"
    BIRTHDAY = "birthday"
    MEETING = "meeting"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"
    FAVORITE = "favorite"
    ALLERGY = "allergy"
    ROUTINE = "routine"
    IMPORTANT_DATE = "important_date"
    PERSON = "person"
    SLEEP = "sleep"
    EXERCISE = "exercise"
    DIET = "diet"
    PET = "pet"
    FAMILY = "family"


@dataclass
class MemoryPrompt:
    """A prompt to gather missing information."""
    topic: MemoryTopic
    question: str
    question_hinglish: str
    missing_field: str
    context: str = ""
    priority: int = 1  # 1=high, 2=medium, 3=low
    expires_turns: int = 3  # Ask within this many turns


@dataclass
class PendingMemoryQuery:
    """A pending query waiting for user response."""
    topic: MemoryTopic
    missing_field: str
    question_asked: str
    context: dict = field(default_factory=dict)
    asked_at: datetime = field(default_factory=datetime.now)
    turn_count: int = 0


class ProactiveMemoryPrompter:
    """
    Detects incomplete important information and prompts for details.
    
    Handles topics like:
    - Medicine names and schedules
    - Birthdays and important dates
    - Meetings and appointments
    - Favorites and preferences
    - Allergies and health info
    """
    
    # Detection patterns for each topic
    TOPIC_PATTERNS = {
        MemoryTopic.MEDICINE: [
            r"(?:medicine|dawai|tablet|pill|goli|दवाई|दवा|टेबलेट|गोली|खानी|खाना)\b",
            r"(?:take|lena|leni|khana|khani)\s+(?:my|meri|apni)?\s*(?:medicine|dawai)",
            r"(?:doctor|doc)\s+(?:ne|gave|diya|di)",
            r"(?:prescription|nuskha)",
            r"(?:pharmacy|medical|chemist)",
            # Also detect common medicine names
            r"\b(?:paracetamol|crocin|aspirin|disprin|ibuprofen|cetirizine|metformin|omeprazole|azithromycin|pantoprazole|dolo|saridon|combiflam)\b",
        ],
        MemoryTopic.BIRTHDAY: [
            r"(?:birthday|bday|janmdin|janamdin)\b",
            r"(?:born|paida)\s+(?:on|ko|pe)",
            r"(?:age|umar|umr)\s+(?:hai|is|ho)",
        ],
        MemoryTopic.MEETING: [
            r"(?:meeting|call|zoom|teams)\b",
            r"(?:office|work)\s+(?:pe|mein|at)\s+(?:meeting|call)",
            r"\b(?:sync|standup|stand-up)\b",
            r"(?:video\s*call|conference)",
        ],
        MemoryTopic.APPOINTMENT: [
            r"(?:appointment|dentist|clinic)\b",
            r"(?:checkup|check-up|check up)\b",
            r"\bhospital\b",
            r"(?:doctor)\s+(?:ke paas|visit)",
        ],
        MemoryTopic.FAVORITE: [
            r"(?:favourite|favorite|fav|pasand|best)\s+(\w+)",
            r"(?:love|pyaar|like)\s+(?:karta|karti|करता|करती)?\s*(\w+)",
        ],
        MemoryTopic.ALLERGY: [
            r"(?:allergy|allergic|एलर्जी)\b",
            r"(?:can't eat|nahi kha sakta|nahi khati)\b",
            r"\ballergy\s+hai\b",
        ],
        MemoryTopic.ROUTINE: [
            r"(?:daily|roz|everyday|har din)\s+(?:routine|kaam)",
            r"(?:morning|subah|evening|shaam)\s+(?:routine|ritual)",
            r"(?:workout|exercise|gym)\s+(?:karta|karti|करता)",
        ],
        MemoryTopic.IMPORTANT_DATE: [
            r"(?:anniversary|saalgirah)\b",
            r"(?:exam|परीक्षा|test)\s+(?:hai|is|on)",
            r"(?:deadline|due date)\b",
        ],
        MemoryTopic.SLEEP: [
            r"(?:sleep|sona|neend|soyi|soya|soti|sota)\b",
            r"(?:insomnia|can't sleep|nahi aati neend)\b",
            r"(?:wake up|uthna|uthti|jagti|jagta)\b",
            r"\b(?:late|jaldi)\s+(?:soti|sota|sona|so)\b",
            r"\bsone\s+(?:mein|ki)\b",
            r"\bso\s+(?:jaati|jaata|gaya|gayi)\b",
        ],
        MemoryTopic.EXERCISE: [
            r"(?:gym|workout|exercise|yoga)\b",
            r"(?:run|running|jogging|walk|walking)\b",
            r"(?:fitness|fit)\b",
            r"\b(?:swim|swimming|cycling|cycle)\b",
        ],
        MemoryTopic.DIET: [
            r"(?:diet|dieting|kha rahi|kha raha)\b",
            r"(?:weight loss|weight gain|vajan)\b",
            r"(?:calories|protein|carbs)\b",
        ],
        MemoryTopic.PET: [
            r"(?:pet|dog|cat|puppy|kitten|kutte|billi)\b",
            r"(?:my pet|mera pet|meri billi|mera kutta)\b",
        ],
        MemoryTopic.FAMILY: [
            r"(?:mom|dad|mummy|papa|mother|father)\b",
            r"(?:brother|sister|bhai|behen|didi)\b",
            r"(?:family|parivaar|ghar wale)\b",
        ],
    }
    
    # Questions to ask for missing information
    FOLLOW_UP_QUESTIONS = {
        MemoryTopic.MEDICINE: {
            "name": [
                "Kaun si medicine baby?",
                "Arre konsi dawai hai?",
                "Medicine ka naam kya hai?",
                "Kya naam hai dawai ka?",
            ],
            "time": [
                "Kitne baje leni hai?",
                "Kab leni hai medicine?",
                "Time kya hai dawai ka?",
            ],
            "frequency": [
                "Din mein kitni baar?",
                "Kitni baar leni hai?",
            ],
        },
        MemoryTopic.BIRTHDAY: {
            "date": [
                "Kab hai birthday baby?",
                "Date kya hai?",
                "Birthday kab aata hai?",
            ],
        },
        MemoryTopic.MEETING: {
            "time": [
                "Kitne baje hai meeting?",
                "Time kya hai?",
                "Kab hai call?",
            ],
            "topic": [
                "Kis baare mein hai meeting?",
                "What's the meeting about?",
            ],
        },
        MemoryTopic.APPOINTMENT: {
            "time": [
                "Appointment kitne baje hai?",
                "Kab jana hai?",
            ],
            "location": [
                "Kahan jana hai?",
                "Which clinic/hospital?",
            ],
        },
        MemoryTopic.ALLERGY: {
            "item": [
                "Kis cheez se allergy hai?",
                "Allergic to what baby?",
            ],
        },
        MemoryTopic.SLEEP: {
            "time": [
                "Kitne baje soti ho usually?",
                "What time do you sleep?",
            ],
            "wake_time": [
                "Aur kitne baje uthti ho?",
                "When do you wake up?",
            ],
        },
        MemoryTopic.EXERCISE: {
            "type": [
                "Kya karti ho workout?",
                "What kind of exercise?",
            ],
            "schedule": [
                "Kab jaati ho gym?",
                "When do you workout?",
            ],
        },
        MemoryTopic.PET: {
            "name": [
                "Aww! Pet ka naam kya hai?",
                "What's your pet's name?",
            ],
            "type": [
                "Kaisa pet hai? Dog, cat?",
                "What kind of pet?",
            ],
        },
        MemoryTopic.FAMILY: {
            "name": [
                "Unka naam kya hai?",
                "What's their name?",
            ],
        },
    }
    
    # Common medicine names (case insensitive matching)
    COMMON_MEDICINES = {
        "paracetamol", "crocin", "aspirin", "disprin", "ibuprofen",
        "cetirizine", "metformin", "omeprazole", "azithromycin", "pantoprazole",
        "dolo", "saridon", "combiflam", "vicks", "strepsils", "digene",
        "gelusil", "eno", "hajmola", "pudinhara", "volini", "moov",
        "zandu", "benadryl", "allegra", "levocet", "montek", "montair",
        "avil", "sinarest", "d-cold", "vaporub", "amoxicillin", "augmentin",
        "azee", "azax", "clarithromycin", "erythromycin", "doxycycline",
        "ciprofloxacin", "norfloxacin", "ofloxacin", "levofloxacin",
        "ranitidine", "famotidine", "esomeprazole", "rabeprazole",
        "atorvastatin", "rosuvastatin", "amlodipine", "losartan", "telmisartan",
        "glimepiride", "sitagliptin", "vildagliptin", "metformin", "glycomet",
        "thyronorm", "eltroxin", "shelcal", "calcimax", "limcee", "revital",
        "becosules", "neurobion", "folic", "iron", "zinc", "calcium",
    }
    
    # Common allergy items
    COMMON_ALLERGENS = {
        "peanut", "peanuts", "dust", "milk", "dairy", "pollen", "seafood",
        "shellfish", "fish", "gluten", "wheat", "egg", "eggs", "soy", "tree nuts",
        "mold", "pet dander", "cat", "dog", "latex", "penicillin", "sulfa",
    }
    
    # Common pet names (to detect when pet name is given)
    COMMON_PET_NAMES = {
        "tommy", "bruno", "oscar", "max", "buddy", "charlie", "rocky", "leo",
        "whiskers", "fluffy", "milo", "simba", "kitty", "tiger", "mittens",
        "sheru", "moti", "kalu", "bholu", "raja",
    }
    
    # Patterns to detect if information is already provided
    INFO_PRESENT_PATTERNS = {
        "medicine_name": [
            # Medicine name - will be checked against COMMON_MEDICINES
            r"\b([A-Z][a-z]{3,})\b",  # Any capitalized word
        ],
        "medicine_name_simple": [
            r"^([A-Z][a-z]{2,})$",  # Just a capitalized word
        ],
        "time": [
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|baje)?)",
            r"(?:at|around|ko)\s+(\d{1,2})",
        ],
        "time_word": [
            # Time words (morning, evening, etc.) - case insensitive match done separately
            r"\b(morning|subah|evening|shaam|night|raat|afternoon|dopahar|midnight)\b",
        ],
        "date": [
            r"(\d{1,2}(?:st|nd|rd|th)?\s*(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))",
            r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)",
        ],
        "allergen": [
            r"\b([a-zA-Z]+)\s+(?:allergy|allergic|se allergy)",
        ],
        "pet_name": [
            r"\b(?:named?|naam)\s+([A-Z][a-z]+)",
            r"\b([A-Z][a-z]+)\s+(?:naam hai|hai naam)",
        ],
    }
    
    def __init__(self, supabase_client: Any | None = None):
        """Initialize the proactive memory prompter."""
        self._supabase = supabase_client
        
        # Pending queries per session
        self._pending_queries: dict[str, list[PendingMemoryQuery]] = {}
        
        # Compile patterns
        self._topic_patterns = {
            topic: [re.compile(p, re.IGNORECASE) for p in patterns]
            for topic, patterns in self.TOPIC_PATTERNS.items()
        }
        
        self._info_patterns = {
            field: [re.compile(p) for p in patterns]  # NOT case insensitive for medicine names
            for field, patterns in self.INFO_PRESENT_PATTERNS.items()
        }
        
        logger.info("proactive_memory_prompter_initialized")
    
    def detect_memory_topics(self, text: str) -> list[MemoryTopic]:
        """Detect which memory-worthy topics are mentioned."""
        detected = []
        
        for topic, patterns in self._topic_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    detected.append(topic)
                    break
        
        return detected
    
    def check_info_present(self, text: str, field: str) -> tuple[bool, str | None]:
        """
        Check if specific information is already present in text.
        
        Returns:
            (is_present, extracted_value)
        """
        text_lower = text.lower()
        
        # Special handling for medicine names - check against known medicines
        if field == "medicine_name":
            # First check against common medicine names
            for med in self.COMMON_MEDICINES:
                if med.lower() in text_lower:
                    return True, med.capitalize()
            # Fall back to pattern matching for unknown medicines - but be strict
            patterns = self._info_patterns.get(field, [])
            # Words to exclude (common Hindi/English words that aren't medicine names)
            common_words = {
                "mein", "hai", "hoon", "baje", "subah", "shaam", "raat", "morning", 
                "evening", "night", "leti", "lete", "khati", "take", "daily",
                "mujhe", "mera", "meri", "main", "aaj", "kal", "abhi", "pharmacy",
                "medical", "chemist", "doctor", "tablet", "medicine", "dawai", "goli",
                "bahut", "mehengi", "taste", "bura", "leni", "lena", "khani", "khana",
                "store", "jana", "aana", "hona", "karna", "need", "have", "taking",
            }
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    # Verify it looks like a medicine (capitalized, not a common word)
                    if len(value) >= 4 and value.lower() not in common_words:
                        return True, value.strip()
            return False, None
        
        # Special handling for time - check time words too
        if field == "time":
            # Check numeric time patterns
            patterns = self._info_patterns.get("time", [])
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return True, value.strip()
            
            # Check time words (morning, subah, etc.) - use raw pattern string with IGNORECASE
            time_word_patterns = self.INFO_PRESENT_PATTERNS.get("time_word", [])
            for pattern_str in time_word_patterns:
                match = re.search(pattern_str, text, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return True, value.strip()
            
            return False, None
        
        # Special handling for date - use raw pattern string with IGNORECASE
        if field == "date":
            date_patterns = self.INFO_PRESENT_PATTERNS.get("date", [])
            for pattern_str in date_patterns:
                match = re.search(pattern_str, text, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return True, value.strip()
            return False, None
        
        # Special handling for allergens
        if field == "allergen":
            # Check against common allergens
            for allergen in self.COMMON_ALLERGENS:
                if allergen.lower() in text_lower:
                    return True, allergen
            # Fall back to patterns - use raw pattern string with IGNORECASE
            allergen_patterns = self.INFO_PRESENT_PATTERNS.get("allergen", [])
            for pattern_str in allergen_patterns:
                match = re.search(pattern_str, text, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    if len(value) >= 3:
                        return True, value.strip()
            return False, None
        
        # Special handling for pet names
        if field == "pet_name":
            # Check against common pet names
            for pet_name in self.COMMON_PET_NAMES:
                if pet_name.lower() in text_lower:
                    return True, pet_name.capitalize()
            # Fall back to patterns
            patterns = self._info_patterns.get("pet_name", [])
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    return True, value.strip()
            return False, None
        
        # Default pattern matching
        patterns = self._info_patterns.get(field, [])
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                return True, value.strip()
        
        return False, None
    
    def analyze_for_memory_prompts(
        self,
        text: str,
        session_id: str,
        recent_messages: list[dict] | None = None
    ) -> MemoryPrompt | None:
        """
        Analyze text and return a follow-up question if information is incomplete.
        
        Args:
            text: Current user message
            session_id: Session identifier
            recent_messages: Recent conversation for context
            
        Returns:
            MemoryPrompt if follow-up needed, None otherwise
        """
        # Check for pending queries first
        pending = self._check_pending_response(text, session_id)
        if pending:
            return None  # User is responding to a previous question
        
        # Detect topics
        topics = self.detect_memory_topics(text)
        
        if not topics:
            return None
        
        # Check each topic for missing information
        for topic in topics:
            prompt = self._check_topic_completeness(text, topic, recent_messages)
            if prompt:
                # Track that we're asking
                self._add_pending_query(session_id, prompt)
                return prompt
        
        return None
    
    def _check_topic_completeness(
        self,
        text: str,
        topic: MemoryTopic,
        recent_messages: list[dict] | None = None
    ) -> MemoryPrompt | None:
        """Check if topic has complete information, return prompt if not."""
        
        if topic == MemoryTopic.MEDICINE:
            # Check for medicine name
            has_name, name = self.check_info_present(text, "medicine_name")
            
            if not has_name:
                # Also check recent messages
                if recent_messages:
                    for msg in recent_messages[-5:]:
                        has_name, name = self.check_info_present(
                            msg.get("content", ""), "medicine_name"
                        )
                        if has_name:
                            break
            
            if not has_name:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["name"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="medicine_name",
                    context=text,
                    priority=1
                )
            
            # Check for time
            has_time, time_val = self.check_info_present(text, "time")
            if not has_time and name:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["time"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="medicine_time",
                    context=f"medicine: {name}",
                    priority=2
                )
        
        elif topic == MemoryTopic.BIRTHDAY:
            has_date, date_val = self.check_info_present(text, "date")
            
            if not has_date:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["date"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="birthday_date",
                    context=text,
                    priority=1
                )
        
        elif topic == MemoryTopic.MEETING:
            has_time, time_val = self.check_info_present(text, "time")
            
            if not has_time:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["time"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="meeting_time",
                    context=text,
                    priority=1
                )
        
        elif topic == MemoryTopic.APPOINTMENT:
            has_time, time_val = self.check_info_present(text, "time")
            
            if not has_time:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["time"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="appointment_time",
                    context=text,
                    priority=1
                )
        
        elif topic == MemoryTopic.ALLERGY:
            # Check if specific allergen mentioned
            has_allergen, allergen = self.check_info_present(text, "allergen")
            
            if not has_allergen:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["item"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="allergy_item",
                    context=text,
                    priority=1
                )
        
        elif topic == MemoryTopic.PET:
            # Check if pet name is mentioned
            has_name, pet_name = self.check_info_present(text, "pet_name")
            
            if not has_name:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["name"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="pet_name",
                    context=text,
                    priority=2
                )
        
        elif topic == MemoryTopic.SLEEP:
            has_time, time_val = self.check_info_present(text, "time")
            
            if not has_time:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["time"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="sleep_time",
                    context=text,
                    priority=3
                )
        
        elif topic == MemoryTopic.EXERCISE:
            # Check if exercise type is mentioned
            exercise_types = ["gym", "yoga", "running", "jogging", "swimming", "cycling", "walk"]
            type_found = any(t in text.lower() for t in exercise_types)
            
            if not type_found:
                import random
                questions = self.FOLLOW_UP_QUESTIONS[topic]["type"]
                return MemoryPrompt(
                    topic=topic,
                    question=random.choice(questions),
                    question_hinglish=random.choice(questions),
                    missing_field="exercise_type",
                    context=text,
                    priority=3
                )
        
        return None
    
    def _add_pending_query(self, session_id: str, prompt: MemoryPrompt):
        """Add a pending query for tracking."""
        if session_id not in self._pending_queries:
            self._pending_queries[session_id] = []
        
        query = PendingMemoryQuery(
            topic=prompt.topic,
            missing_field=prompt.missing_field,
            question_asked=prompt.question,
            context={"original_context": prompt.context}
        )
        
        self._pending_queries[session_id].append(query)
        
        # Keep only recent queries
        if len(self._pending_queries[session_id]) > 5:
            self._pending_queries[session_id] = self._pending_queries[session_id][-5:]
    
    def _check_pending_response(self, text: str, session_id: str) -> PendingMemoryQuery | None:
        """
        Check if user is responding to a pending query.
        
        If yes, extract the information and return the query for saving.
        """
        pending = self._pending_queries.get(session_id, [])
        
        if not pending:
            return None
        
        # Check most recent query
        query = pending[-1]
        
        # Increment turn count
        query.turn_count += 1
        
        # If too many turns, expire
        if query.turn_count > 3:
            pending.pop()
            return None
        
        # Check if response contains the missing info
        if query.missing_field == "medicine_name":
            # Use the improved medicine name detection
            has_name, name = self.check_info_present(text, "medicine_name")
            if has_name and name:
                query.context["answer"] = name
                pending.pop()
                return query
        
        elif query.missing_field in ["medicine_time", "meeting_time", "appointment_time", "sleep_time"]:
            has_time, time_val = self.check_info_present(text, "time")
            if has_time:
                query.context["answer"] = time_val
                pending.pop()
                return query
        
        elif query.missing_field == "birthday_date":
            has_date, date_val = self.check_info_present(text, "date")
            if has_date:
                query.context["answer"] = date_val
                pending.pop()
                return query
        
        elif query.missing_field == "allergy_item":
            has_allergen, allergen = self.check_info_present(text, "allergen")
            if has_allergen:
                query.context["answer"] = allergen
                pending.pop()
                return query
        
        elif query.missing_field == "pet_name":
            has_name, name = self.check_info_present(text, "pet_name")
            if has_name:
                query.context["answer"] = name
                pending.pop()
                return query
        
        return None
    
    async def save_collected_memory(
        self,
        user_id: str,
        query: PendingMemoryQuery,
        memory_service: Any
    ):
        """Save the collected memory information."""
        answer = query.context.get("answer")
        if not answer:
            return
        
        topic = query.topic
        field = query.missing_field
        
        # Determine category and key
        if topic == MemoryTopic.MEDICINE:
            if field == "medicine_name":
                fact = MemoryFact(
                    category=MemoryCategory.MEDICAL,
                    fact_key="medicine_name",
                    fact_value=answer,
                    confidence=0.9,
                    source="proactive_prompt"
                )
            elif field == "medicine_time":
                fact = MemoryFact(
                    category=MemoryCategory.MEDICAL,
                    fact_key="medicine_time",
                    fact_value=answer,
                    confidence=0.9,
                    source="proactive_prompt"
                )
            else:
                return
        
        elif topic == MemoryTopic.BIRTHDAY:
            fact = MemoryFact(
                category=MemoryCategory.PERSONAL,
                fact_key="birthday",
                fact_value=answer,
                confidence=0.9,
                source="proactive_prompt"
            )
        
        elif topic == MemoryTopic.ALLERGY:
            fact = MemoryFact(
                category=MemoryCategory.MEDICAL,
                fact_key="allergy",
                fact_value=answer,
                confidence=0.9,
                source="proactive_prompt"
            )
        
        else:
            # Generic save
            fact = MemoryFact(
                category=MemoryCategory.PERSONAL,
                fact_key=field,
                fact_value=answer,
                confidence=0.8,
                source="proactive_prompt"
            )
        
        # Save using memory service
        await memory_service.save_memory_fact(user_id, fact)
        
        logger.info(
            "proactive_memory_saved",
            topic=topic.value,
            field=field,
            value=answer
        )
    
    def get_pending_queries(self, session_id: str) -> list[PendingMemoryQuery]:
        """Get all pending queries for a session."""
        return self._pending_queries.get(session_id, [])
    
    def clear_session(self, session_id: str):
        """Clear pending queries for a session."""
        self._pending_queries.pop(session_id, None)
    
    def format_question_for_response(self, prompt: MemoryPrompt) -> str:
        """
        Format the question to be naturally included in response.
        
        Returns a natural-sounding question that can be appended to any response.
        """
        # Add some natural connectors
        connectors = [
            "Btw, ",
            "Acha, ",
            "Arre haan, ",
            "Oh wait, ",
            "Ek baat batao, ",
        ]
        
        import random
        connector = random.choice(connectors)
        
        return f"{connector}{prompt.question_hinglish}"
