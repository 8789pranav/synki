"""
Entity Extractor

Extracts entities (movies, people, preferences, etc.) from conversation
for memory persistence and thread tracking.
"""

import re
from datetime import datetime
from typing import Any

import structlog

from .layered_memory import Entity, EntityType, MemoryFact, MemoryCategory

logger = structlog.get_logger(__name__)


class EntityExtractor:
    """
    Extracts named entities and facts from conversation text.
    
    Uses pattern matching and optional LLM enhancement for
    extracting movies, people, places, preferences, etc.
    """
    
    # Common movie/show patterns (Hindi + English) - more flexible for speech
    MOVIE_PATTERNS = [
        r"(?:movie|film|picture|flick)\s+(?:called\s+)?[\"']?([A-Za-z][A-Za-z0-9\s]{1,20})[\"']?",
        r"(?:watched|dekhi|dekhna|watching)\s+[\"']?([A-Za-z][A-Za-z0-9\s]{1,20})[\"']?",
        r"[\"']([A-Za-z][A-Za-z0-9\s]{1,20})[\"']\s+(?:movie|film|dekhi|dekhna)",
        r"(?:show|series|web series|webseries)\s+[\"']?([A-Za-z][A-Za-z0-9\s]{1,20})[\"']?",
        # Hindi patterns for "meri favorite movie X hai"
        r"(?:meri|mera)\s+(?:favourite|favorite|fav)\s+(?:movie|film)\s+([A-Za-z][A-Za-z0-9\s]{1,20})\s+(?:hai|he|h)",
        r"(?:favourite|favorite|fav)\s+(?:movie|film)\s+(?:hai|is|he)?\s*([A-Za-z][A-Za-z0-9\s]{1,20})",
        r"(?:movie|film)\s+([A-Za-z][A-Za-z0-9\s]{1,20})\s+(?:bahut|bohot|bht|kaafi)\s+(?:acchi|achi|mast|best)",
    ]
    
    # Person name patterns - more flexible
    PERSON_PATTERNS = [
        r"(?:friend|dost|yaar|bro|brother|sister|mom|dad|mummy|papa|bf|gf)\s+(?:ka naam|named|called)?\s*([A-Za-z][a-z]+)",
        r"([A-Za-z][a-z]+)\s+(?:ka|ki|ke)\s+(?:saath|with)",
        r"(?:mera|meri|mere)\s+(?:friend|dost|yaar)\s+([A-Za-z][a-z]+)",
        r"(?:naam|name)\s+(?:hai|is)?\s*([A-Za-z][a-z]+)",
    ]
    
    # Food patterns - more flexible
    FOOD_PATTERNS = [
        r"(?:favourite|favorite|pasand|fav)\s+(?:food|khana|dish)\s+(?:hai|is)?\s*[\"']?([A-Za-z][A-Za-z\s]+)[\"']?",
        r"(?:love|pyaar|acchi lagti|pasand)\s+(?:eating|khana)?\s*[\"']?([A-Za-z][A-Za-z\s]+)[\"']?",
        r"(?:khana|food|eat|khaunga|khaungi)\s+[\"']?([A-Za-z][A-Za-z\s]+)[\"']?",
        # Hindi patterns
        r"(?:mujhe|meko)\s+([A-Za-z][A-Za-z\s]+)\s+(?:bahut|bohot|bht)?\s*(?:pasand|accha|achha|mast)",
        r"(?:favourite|favorite|fav)\s+(?:food|khana)\s+([A-Za-z][A-Za-z\s]+)\s+(?:hai|he|h)",
    ]
    
    # Medicine/health patterns - more flexible
    MEDICINE_PATTERNS = [
        r"(?:take|lena|leti|lete|leta)\s+([A-Za-z][a-z]+(?:ol|in|ide|ate|cin|ine|one|pam|lam|tan|ex|en)?)",
        r"([A-Za-z][a-z]+(?:ol|in|ide|ate|cin|ine|one|pam|lam|tan|ex|en))\s+(?:tablet|medicine|dawai|di|diya)",
        r"(?:medicine|dawai|tablet)\s+(?:called|naam)?\s*([A-Za-z][a-z]+)",
        r"(?:doctor|doc)\s+(?:ne|gave|diya)\s+([A-Za-z][a-z]+)",
        # Hindi patterns
        r"(?:meri|mera)\s+(?:medicine|dawai|tablet)\s+([A-Za-z][a-z]+)",
        r"(?:daily|roz|rozana)\s+([A-Za-z][a-z]+)\s+(?:leti|leta|lena|khati|khata)",
    ]
    
    # Time-related patterns  
    TIME_PATTERNS = [
        r"(?:at|around|baje|ko)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|baje)?)",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        r"(?:morning|subah|evening|shaam|night|raat)\s+(?:ko|at)?\s*(\d{1,2}(?::\d{2})?)",
    ]
    
    # Hobby/activity patterns
    HOBBY_PATTERNS = [
        r"(?:hobby|hobbies|pastime)\s+(?:hai|is|are)?\s*[\"']?([A-Za-z\s,]+)[\"']?",
        r"(?:love|enjoy|like)\s+(?:to)?\s+((?:reading|writing|gaming|cooking|dancing|singing|drawing|painting|swimming|running|cycling|yoga|gym|music)[A-Za-z\s]*)",
        r"(?:mujhe|i)\s+(?:pasand|like)\s+(?:hai|is)?\s+((?:padna|likhna|khelna|nachna|gaana)[A-Za-z\s]*)",
    ]
    
    # Preference patterns (likes/dislikes) - MORE FLEXIBLE for "favorite X is Y"
    PREFERENCE_PATTERNS = [
        # English: "My favorite movie is Sholay", "favorite food is pizza"
        r"(?:my\s+)?(?:favourite|favorite|fav)\s+(\w+)\s+(?:is|hai|he)\s+[\"']?([A-Za-z0-9][A-Za-z0-9\s]*)[\"']?",
        # Hindi: "meri favorite movie Sholay hai"
        r"(?:meri|mera|mere)\s+(?:favourite|favorite|fav)\s+(\w+)\s+([A-Za-z0-9][A-Za-z0-9\s]+)\s+(?:hai|he|h)",
        # "favorite movie Sholay" (without is/hai)
        r"(?:favourite|favorite|fav)\s+(\w+)\s+([A-Za-z0-9][A-Za-z0-9\s]+)",
        # General like/love patterns
        r"(?:i|mujhe|main|me)\s+(?:love|hate|like|dislike|pasand|nafrat)\s+[\"']?([A-Za-z0-9][A-Za-z0-9\s]+)[\"']?",
        r"(?:don't|nahi|nhi)\s+(?:like|pasand)\s+[\"']?([A-Za-z0-9][A-Za-z0-9\s]+)[\"']?",
    ]
    
    # Work-related patterns
    WORK_PATTERNS = [
        r"(?:work|kaam|job|naukri)\s+(?:at|pe|mein|in)\s+[\"']?([A-Za-z0-9\s]+)[\"']?",
        r"(?:i'm a|main|i am)\s+(?:a)?\s*([A-Za-z\s]+(?:engineer|developer|designer|manager|teacher|doctor|student))",
        r"(?:company|office)\s+(?:ka naam|named|called)?\s*[\"']?([A-Za-z0-9\s]+)[\"']?",
    ]
    
    # Relationship patterns
    RELATIONSHIP_PATTERNS = [
        r"(?:boyfriend|bf|girlfriend|gf|husband|wife|partner)\s+(?:ka naam|named|called)?\s*([A-Z][a-z]+)",
        r"(?:relationship|dating|married)\s+(?:with|se)?\s*([A-Z][a-z]+)",
    ]
    
    def __init__(self, llm_client: Any | None = None):
        """
        Initialize entity extractor.
        
        Args:
            llm_client: Optional LLM client for enhanced extraction
        """
        self._llm = llm_client
        
        # Compile patterns
        self._patterns = {
            EntityType.MOVIE: [re.compile(p, re.IGNORECASE) for p in self.MOVIE_PATTERNS],
            EntityType.PERSON: [re.compile(p, re.IGNORECASE) for p in self.PERSON_PATTERNS],
            EntityType.FOOD: [re.compile(p, re.IGNORECASE) for p in self.FOOD_PATTERNS],
            EntityType.MEDICINE: [re.compile(p, re.IGNORECASE) for p in self.MEDICINE_PATTERNS],
            EntityType.TIME: [re.compile(p, re.IGNORECASE) for p in self.TIME_PATTERNS],
            EntityType.ACTIVITY: [re.compile(p, re.IGNORECASE) for p in self.HOBBY_PATTERNS],
        }
        
        # Additional patterns for memory facts
        self._fact_patterns = {
            "preference": [re.compile(p, re.IGNORECASE) for p in self.PREFERENCE_PATTERNS],
            "work": [re.compile(p, re.IGNORECASE) for p in self.WORK_PATTERNS],
            "relationship": [re.compile(p, re.IGNORECASE) for p in self.RELATIONSHIP_PATTERNS],
        }
        
        logger.info("entity_extractor_initialized")
    
    def extract_entities(self, text: str) -> list[Entity]:
        """
        Extract all entities from text using pattern matching.
        
        Args:
            text: Input text to extract entities from
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        for entity_type, patterns in self._patterns.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                for match in matches:
                    value = match.strip() if isinstance(match, str) else match[0].strip()
                    if value and len(value) > 1:
                        # Clean up the value
                        value = self._clean_entity_value(value)
                        if value:
                            entities.append(Entity(
                                type=entity_type,
                                value=value,
                                confidence=0.7,
                                mentioned_at=datetime.now()
                            ))
        
        # Deduplicate by type and value
        seen = set()
        unique_entities = []
        for entity in entities:
            key = (entity.type, entity.value.lower())
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        if unique_entities:
            logger.info(
                "entities_extracted",
                count=len(unique_entities),
                types=[e.type.value for e in unique_entities],
                values=[e.value for e in unique_entities],
                source_text=text[:100]
            )
        else:
            logger.debug("no_entities_found", text_preview=text[:50])
        
        return unique_entities
    
    def extract_memory_facts(self, text: str) -> list[MemoryFact]:
        """
        Extract durable memory facts from text.
        
        These are things like preferences, job info, relationships
        that should be remembered long-term.
        """
        facts = []
        
        # Preference extraction
        for pattern in self._fact_patterns["preference"]:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    category_hint, value = match[0], match[1]
                    facts.append(MemoryFact(
                        category=MemoryCategory.PREFERENCE,
                        fact_key=f"favorite_{category_hint.lower()}",
                        fact_value=value.strip(),
                        confidence=0.7
                    ))
        
        # Work extraction
        for pattern in self._fact_patterns["work"]:
            matches = pattern.findall(text)
            for match in matches:
                value = match.strip() if isinstance(match, str) else match[0].strip()
                if value:
                    facts.append(MemoryFact(
                        category=MemoryCategory.WORK,
                        fact_key="occupation",
                        fact_value=value,
                        confidence=0.7
                    ))
        
        # Relationship extraction
        for pattern in self._fact_patterns["relationship"]:
            matches = pattern.findall(text)
            for match in matches:
                value = match.strip() if isinstance(match, str) else match[0].strip()
                if value:
                    facts.append(MemoryFact(
                        category=MemoryCategory.RELATIONSHIP,
                        fact_key="partner_name",
                        fact_value=value,
                        confidence=0.7
                    ))
        
        if facts:
            logger.info(
                "facts_extracted",
                count=len(facts),
                categories=[f.category.value for f in facts],
                keys=[f.fact_key for f in facts],
                values=[f.fact_value for f in facts],
                source_text=text[:100]
            )
        else:
            logger.debug("no_facts_found", text_preview=text[:50])
        
        return facts
    
    async def extract_with_llm(
        self,
        text: str,
        conversation_history: list[dict] | None = None
    ) -> tuple[list[Entity], list[MemoryFact]]:
        """
        Use LLM for enhanced entity and fact extraction.
        
        This provides better accuracy for complex sentences
        and Hindi/Hinglish/Devanagari text.
        """
        if not self._llm:
            logger.warning("llm_not_available_for_extraction")
            return self.extract_entities(text), self.extract_memory_facts(text)
        
        try:
            # Build context
            history_text = ""
            if conversation_history:
                recent = conversation_history[-5:]
                history_text = "\n".join([
                    f"{m['role']}: {m['content']}" for m in recent
                ])
            
            prompt = f"""Extract entities and memory facts from this Hindi/Hinglish conversation message.

The text may be in Devanagari script (Hindi) or romanized Hinglish. Extract ALL relevant information.

Current message: {text}
{f"Recent context:{chr(10)}{history_text}" if history_text else ""}

Extract these types of information:
1. ENTITIES: movie names, person names, places, food items, medicines, times, activities
2. FACTS: preferences (favorite X), job/work info, relationships, hobbies, medical info, personal details

IMPORTANT PATTERNS to detect (in Hindi/Devanagari or English):
- "मेरी favorite movie X है" → favorite_movie: X
- "favorite place X है" → favorite_place: X
- "मुझे X पसंद है" → likes: X  
- "मैं X में काम करता/करती हूं" → workplace: X
- "मेरा नाम X है" → name: X
- "मैं X खाना पसंद करता हूं" → favorite_food: X
- "मेरा birthday X में है" → birthday_month: X
- "X मेरी favorite है" → favorite: X (determine type from context)
- Anything mentioning "favorite" or "पसंद" should be extracted as a fact!

Return as JSON (use English keys, values can be in original language):
{{
  "entities": [
    {{"type": "movie|person|place|food|medicine|time|activity", "value": "extracted value", "confidence": 0.8}}
  ],
  "facts": [
    {{"category": "preference|habit|personal|medical|hobby|work|relationship", "key": "favorite_movie|favorite_food|favorite_place|workplace|name|likes|birthday|etc", "value": "extracted value", "confidence": 0.8}}
  ]
}}

RULES:
- If user mentions "favorite X" or "पसंद", ALWAYS create a fact with key "favorite_X" or "likes"
- Only extract what's EXPLICITLY stated
- Return empty arrays [] if nothing found
- Be accurate, don't hallucinate facts"""

            logger.info("llm_extraction_started", text_preview=text[:50])
            
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=500
            )
            
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info("llm_extraction_result", result=result)
            
            entities = []
            for e in result.get("entities", []):
                try:
                    entities.append(Entity(
                        type=EntityType(e["type"]),
                        value=e["value"],
                        confidence=e.get("confidence", 0.8)
                    ))
                except (KeyError, ValueError):
                    pass
            
            facts = []
            for f in result.get("facts", []):
                try:
                    facts.append(MemoryFact(
                        category=MemoryCategory(f["category"]),
                        fact_key=f["key"],
                        fact_value=f["value"],
                        confidence=f.get("confidence", 0.8)
                    ))
                except (KeyError, ValueError):
                    pass
            
            if entities or facts:
                logger.info(
                    "llm_extraction_success",
                    entities_count=len(entities),
                    facts_count=len(facts),
                )
            
            return entities, facts
            
        except Exception as e:
            logger.error("llm_extraction_failed", error=str(e))
            # Fallback to pattern matching
            return self.extract_entities(text), self.extract_memory_facts(text)
    
    def detect_entity_references(self, text: str) -> list[tuple[EntityType, str]]:
        """
        Detect vague entity references that need resolution.
        
        Returns list of (entity_type, reference_phrase) tuples.
        """
        references = []
        
        # Movie references
        movie_refs = [
            r"(?:that|वो|wo|woh)\s+(?:movie|film)",
            r"(?:the|वो|wo)\s+(?:one|wali|waali)",
            r"(?:same|wahi|wohi)\s+(?:movie|film)",
            r"usme\s+(?:kya|what)",  # "in that/it what"
        ]
        
        for pattern in movie_refs:
            if re.search(pattern, text, re.IGNORECASE):
                references.append((EntityType.MOVIE, pattern))
        
        # Person references
        person_refs = [
            r"(?:that|वो|wo)\s+(?:person|banda|ladka|ladki|friend)",
            r"(?:usko|usse|unko)\b",  # "him/her/them"
        ]
        
        for pattern in person_refs:
            if re.search(pattern, text, re.IGNORECASE):
                references.append((EntityType.PERSON, pattern))
        
        # Medicine references
        medicine_refs = [
            r"(?:that|वो|wo)\s+(?:medicine|dawai|tablet)",
            r"(?:same|wahi)\s+(?:medicine|dawai)",
        ]
        
        for pattern in medicine_refs:
            if re.search(pattern, text, re.IGNORECASE):
                references.append((EntityType.MEDICINE, pattern))
        
        return references
    
    def _clean_entity_value(self, value: str) -> str:
        """Clean and normalize entity value."""
        # Remove extra whitespace
        value = " ".join(value.split())
        
        # Remove common articles
        value = re.sub(r"^(?:a|an|the|ek|yeh|woh)\s+", "", value, flags=re.IGNORECASE)
        
        # Remove trailing punctuation
        value = value.rstrip(".,!?;:")
        
        # Skip if too short or common word
        if len(value) < 2:
            return ""
        
        common_words = {
            "it", "that", "this", "what", "how", "why", "when", "where",
            "kya", "kaise", "kyun", "kab", "kahan", "ye", "wo", "hai"
        }
        if value.lower() in common_words:
            return ""
        
        return value
    
    def classify_message_intent(self, text: str) -> dict:
        """
        Analyze message for memory-related intent.
        
        Returns dict with:
        - is_sharing_info: User is sharing personal info
        - is_asking_recall: User wants us to remember something
        - is_referencing: User is referencing something mentioned before
        - memory_action: What memory action to take
        """
        result = {
            "is_sharing_info": False,
            "is_asking_recall": False,
            "is_referencing": False,
            "memory_action": None
        }
        
        # Sharing patterns
        sharing_patterns = [
            r"(?:my|mera|meri|mere)\s+(?:name|naam|favorite|favourite|hobby|job|work)",
            r"(?:i|main|mujhe)\s+(?:am|hu|hoon|like|love|hate|work|live)",
            r"(?:my|mera)\s+(?:birthday|janmdin)\s+(?:hai|is)",
        ]
        
        for pattern in sharing_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result["is_sharing_info"] = True
                result["memory_action"] = "store"
                break
        
        # Recall request patterns
        recall_patterns = [
            r"(?:yaad|remember|recall)\s+(?:hai|rakh|karo|rakho)",
            r"(?:don't forget|mat bhulna|bhoolna mat)",
            r"(?:save|note)\s+(?:this|ye|yeh|kar|karo)",
        ]
        
        for pattern in recall_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result["is_asking_recall"] = True
                result["memory_action"] = "store_important"
                break
        
        # Reference patterns
        reference_patterns = [
            r"(?:remember|yaad)\s+(?:when|jab)",
            r"(?:like|jaise)\s+(?:last time|pichli baar)",
            r"(?:that|वो|wo)\s+(?:time|baar|day|din)",
            r"(?:what|kya)\s+(?:was|tha)\s+(?:that|वो)",
        ]
        
        for pattern in reference_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result["is_referencing"] = True
                result["memory_action"] = "recall"
                break
        
        return result
