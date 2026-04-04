"""
Summary Generator

Creates summaries of conversations for:
- Session summaries (end of conversation)
- Daily summaries (aggregating sessions)
- Weekly summaries (aggregating days)
- Thread summaries (topic-specific)
"""

import json
from datetime import datetime, timedelta
from typing import Any

import structlog

from .layered_memory import Entity, MemoryFact

logger = structlog.get_logger(__name__)


class SummaryGenerator:
    """
    Generates conversation summaries at different granularities.
    
    Uses LLM for intelligent summarization while extracting
    key topics, entities, and emotional themes.
    """
    
    def __init__(
        self,
        llm_client: Any | None = None,
        supabase_client: Any | None = None,
        openai_client: Any | None = None
    ):
        """Initialize summary generator."""
        self._llm = llm_client or openai_client
        self._supabase = supabase_client
        
        logger.info("summary_generator_initialized")
    
    async def generate_session_summary(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict],
        entities: list[Entity] | None = None,
        facts_learned: list[MemoryFact] | None = None
    ) -> dict:
        """
        Generate a summary for a conversation session.
        
        Returns:
            Dict with summary_text, key_topics, key_entities, emotional_arc
        """
        if not messages:
            return {
                "summary_text": "",
                "key_topics": [],
                "key_entities": [],
                "emotional_arc": "neutral"
            }
        
        # Try LLM summarization first
        if self._llm:
            try:
                return await self._llm_summarize_session(
                    messages, entities, facts_learned
                )
            except Exception as e:
                logger.error("llm_summary_failed", error=str(e))
        
        # Fallback to simple extraction
        return self._simple_summarize(messages, entities, facts_learned)
    
    async def _llm_summarize_session(
        self,
        messages: list[dict],
        entities: list[Entity] | None = None,
        facts_learned: list[MemoryFact] | None = None
    ) -> dict:
        """Use LLM for intelligent summarization."""
        # Format conversation
        conversation_text = "\n".join([
            f"{m['role'].upper()}: {m['content']}" 
            for m in messages[-30:]  # Last 30 messages
        ])
        
        entity_list = ", ".join([
            f"{e.type.value}: {e.value}" for e in (entities or [])
        ]) or "none"
        
        facts_list = ", ".join([
            f"{f.fact_key}: {f.fact_value}" for f in (facts_learned or [])
        ]) or "none"
        
        prompt = f"""Summarize this Hinglish conversation between a user and their AI companion (girlfriend-style).

Conversation:
{conversation_text}

Entities mentioned: {entity_list}
Facts learned: {facts_list}

Provide a JSON response with:
1. summary_text: 2-3 sentence summary in Hinglish
2. key_topics: Array of main topics discussed (max 5)
3. key_entities: Array of {{type, value}} for important entities
4. emotional_arc: One of "positive", "negative", "mixed", "neutral"
5. pending_followup: Any question or topic left hanging (null if none)

Keep the summary natural and conversational."""

        response = await self._llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=500
        )
        
        result = json.loads(response.choices[0].message.content)
        return {
            "summary_text": result.get("summary_text", ""),
            "key_topics": result.get("key_topics", []),
            "key_entities": result.get("key_entities", []),
            "emotional_arc": result.get("emotional_arc", "neutral"),
            "pending_followup": result.get("pending_followup")
        }
    
    def _simple_summarize(
        self,
        messages: list[dict],
        entities: list[Entity] | None = None,
        facts_learned: list[MemoryFact] | None = None
    ) -> dict:
        """Simple rule-based summarization fallback."""
        # Extract topics from messages
        topics = set()
        for msg in messages:
            content = msg.get("content", "").lower()
            if any(w in content for w in ["movie", "film", "show"]):
                topics.add("movies")
            if any(w in content for w in ["work", "office", "job"]):
                topics.add("work")
            if any(w in content for w in ["food", "khana", "eat"]):
                topics.add("food")
            if any(w in content for w in ["health", "doctor", "medicine"]):
                topics.add("health")
        
        # Basic summary
        msg_count = len(messages)
        user_msgs = [m for m in messages if m.get("role") == "user"]
        
        summary = f"Had a conversation with {msg_count} messages."
        if topics:
            summary += f" Discussed {', '.join(topics)}."
        
        return {
            "summary_text": summary,
            "key_topics": list(topics)[:5],
            "key_entities": [
                {"type": e.type.value, "value": e.value}
                for e in (entities or [])[:5]
            ],
            "emotional_arc": "neutral",
            "pending_followup": None
        }
    
    async def generate_thread_summary(
        self,
        thread_id: str,
        thread_type: str,
        messages: list[dict],
        entities: list[Entity]
    ) -> str:
        """Generate a summary for a conversation thread."""
        if not self._llm:
            return f"Thread about {thread_type} with {len(entities)} entities mentioned."
        
        try:
            conversation = "\n".join([
                f"{m['role']}: {m['content']}" 
                for m in messages[-15:]
            ])
            
            entities_str = ", ".join([e.value for e in entities[:5]])
            
            prompt = f"""Summarize this thread discussion in 1-2 sentences.
            
Thread type: {thread_type}
Key entities: {entities_str}

Conversation:
{conversation}

Write a natural, brief summary in Hinglish."""

            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error("thread_summary_failed", error=str(e))
            return ""
    
    async def save_session_summary(
        self,
        user_id: str,
        session_id: str,
        summary: dict
    ):
        """Save session summary to database."""
        if not self._supabase:
            return
        
        try:
            # Create embedding for the summary
            embedding = None
            if self._llm and summary.get("summary_text"):
                try:
                    embed_response = await self._llm.embeddings.create(
                        model="text-embedding-ada-002",
                        input=summary["summary_text"]
                    )
                    embedding = embed_response.data[0].embedding
                except:
                    pass
            
            await self._supabase.table("memory_summaries").insert({
                "user_id": user_id,
                "summary_type": "session",
                "session_id": session_id,
                "summary_text": summary.get("summary_text", ""),
                "key_topics": summary.get("key_topics", []),
                "key_entities": summary.get("key_entities", []),
                "embedding": embedding
            }).execute()
            
            logger.info("session_summary_saved", session_id=session_id)
        except Exception as e:
            logger.error("summary_save_failed", error=str(e))
    
    async def generate_daily_summary(
        self,
        user_id: str,
        date: datetime | None = None
    ) -> dict | None:
        """
        Generate a daily summary aggregating all sessions.
        
        Args:
            user_id: User ID
            date: Date to summarize (defaults to today)
            
        Returns:
            Daily summary dict or None if no sessions
        """
        if not self._supabase:
            return None
        
        date = date or datetime.now()
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        
        try:
            # Get session summaries for the day
            result = await self._supabase.table("memory_summaries").select("*").eq(
                "user_id", user_id
            ).eq("summary_type", "session").gte(
                "created_at", start.isoformat()
            ).lt("created_at", end.isoformat()).execute()
            
            if not result.data:
                return None
            
            # Aggregate summaries
            all_topics = []
            all_entities = []
            summaries = []
            
            for row in result.data:
                summaries.append(row.get("summary_text", ""))
                all_topics.extend(row.get("key_topics", []))
                all_entities.extend(row.get("key_entities", []))
            
            # Use LLM to create daily summary if available
            if self._llm:
                try:
                    prompt = f"""Create a brief daily summary from these session summaries:

{chr(10).join(summaries)}

Topics discussed: {', '.join(set(all_topics))}

Write a natural 1-2 sentence daily summary in Hinglish, like a diary entry."""

                    response = await self._llm.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=150
                    )
                    
                    daily_text = response.choices[0].message.content.strip()
                except:
                    daily_text = f"Had {len(result.data)} conversations discussing {', '.join(set(all_topics)[:3])}."
            else:
                daily_text = f"Had {len(result.data)} conversations discussing {', '.join(set(all_topics)[:3])}."
            
            # Save daily summary
            await self._supabase.table("memory_summaries").insert({
                "user_id": user_id,
                "summary_type": "daily",
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "summary_text": daily_text,
                "key_topics": list(set(all_topics))[:10],
                "key_entities": all_entities[:10]
            }).execute()
            
            return {
                "summary_text": daily_text,
                "session_count": len(result.data),
                "key_topics": list(set(all_topics))[:10],
                "key_entities": all_entities[:10],
                "date": date.date().isoformat()
            }
            
        except Exception as e:
            logger.error("daily_summary_failed", error=str(e))
            return None
    
    async def get_recent_summaries(
        self,
        user_id: str,
        summary_type: str = "session",
        limit: int = 5
    ) -> list[dict]:
        """Get recent summaries for context."""
        if not self._supabase:
            return []
        
        try:
            result = await self._supabase.table("memory_summaries").select(
                "summary_text,key_topics,key_entities,created_at"
            ).eq("user_id", user_id).eq(
                "summary_type", summary_type
            ).order("created_at", desc=True).limit(limit).execute()
            
            return result.data or []
        except Exception as e:
            logger.error("summaries_fetch_failed", error=str(e))
            return []
    
    def format_summaries_for_context(self, summaries: list[dict]) -> str:
        """Format summaries into context string for LLM."""
        if not summaries:
            return ""
        
        parts = ["Recent conversation history:"]
        for s in summaries:
            date_str = s.get("created_at", "")[:10]
            text = s.get("summary_text", "")
            if text:
                parts.append(f"- {date_str}: {text}")
        
        return "\n".join(parts)
