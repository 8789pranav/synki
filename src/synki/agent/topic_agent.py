"""
Synki Topic Caller Agent - A soft, caring companion for scheduled topic calls.

This is a SEPARATE agent from the girlfriend companion. It's used when someone
schedules a call for another person with specific topics/questions.

PERSONALITY: Soft, caring, warm friend (NOT girlfriend)
PURPOSE: Greet warmly, ask the scheduled questions, listen with care

NOTE: This agent is registered on the SAME server as companion_agent.
Do not run this file separately - it's imported by companion_agent.py
"""

import asyncio
import structlog
from typing import List, Optional
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import AgentSession, Agent
from livekit.plugins import silero, openai, deepgram

from ..config import settings

load_dotenv(".env.local")

logger = structlog.get_logger(__name__)

# Supabase client - will be set by companion_agent when importing
supabase = None

def set_supabase_client(client):
    """Set the supabase client from companion_agent."""
    global supabase
    supabase = client


class TopicCallerAssistant(Agent):
    """
    A soft, caring companion for topic-based scheduled calls.
    
    NOT a girlfriend - just a warm, friendly helper who:
    1. Greets the person warmly
    2. Explains who scheduled the call
    3. Asks the questions one by one
    4. Listens with care and acknowledges responses
    5. Wraps up gently
    """
    
    def __init__(
        self,
        *,
        user_name: str = "Friend",
        scheduled_by_name: str = "Someone",
        topic_title: str = "check-in",
        topic_prompts: List[str] = None,
        relationship: str = "friend",
        user_id: str | None = None,
    ):
        self.user_name = user_name
        self.scheduled_by_name = scheduled_by_name
        self.topic_title = topic_title
        self.topic_prompts = topic_prompts or ["How are you feeling today?"]
        self.relationship = relationship
        self.user_id = user_id
        self.turn_count = 0
        self.current_question_index = 0
        
        # Build instructions for a soft, caring persona
        instructions = self._build_instructions()
        
        super().__init__(instructions=instructions)
        
        logger.info(
            "topic_caller_initialized",
            user_name=self.user_name,
            scheduled_by=self.scheduled_by_name,
            topic=self.topic_title,
            questions_count=len(self.topic_prompts),
        )
    
    def _build_instructions(self) -> str:
        """Build instructions for a simple, direct helper persona."""
        
        # Format questions for the prompt
        questions_text = "\n".join([f"   {i+1}. {q}" for i, q in enumerate(self.topic_prompts)])
        
        instructions = f"""You are Synki - a simple, helpful assistant. NOT a girlfriend. NOT romantic.

🎯 YOUR ONLY JOB:
{self.scheduled_by_name} asked you to check on {self.user_name} about "{self.topic_title}".
Ask these questions and listen to the answers. That's it.

📋 YOUR QUESTIONS:
{questions_text}

📏 STRICT RULES:
- Be BRIEF and DIRECT
- Ask ONE question at a time
- Listen, acknowledge briefly ("okay", "achha", "theek hai"), move to next
- NO flirting, NO romance, NO girlfriend talk
- NO "baby", "jaanu", "sweetheart" - use "aap" or their name
- NO "aaj kya khas baat hai" or casual chat
- NO long responses - keep it SHORT
- After all questions done, say goodbye and end

❌ ABSOLUTELY DO NOT:
- Ask "aaj kya khas baat hai" or similar
- Be romantic or flirty
- Use girlfriend language
- Chat about random things
- Give lectures or advice
- Say things like "main tumhara intezaar kar rahi thi"

✅ EXAMPLE FLOW:
You: "Hello {self.user_name}, main Synki. {self.scheduled_by_name} ne mujhe bheja hai. [First question]?"
User: [answers]
You: "Achha. [Next question]?"
User: [answers]
You: "Theek hai. [Next question]?"
...
You: "Thank you. {self.scheduled_by_name} ko bata dungi. Bye!"

Keep it simple. Be helpful. Stay on topic."""
        
        return instructions
    
    async def on_user_turn_completed(self, turn_ctx, new_message):
        """Track conversation and guide through questions."""
        user_text = new_message.text_content if hasattr(new_message, 'text_content') else str(new_message)
        
        if not user_text:
            return
        
        self.turn_count += 1
        
        logger.info(
            "topic_call_turn",
            turn=self.turn_count,
            user_text=user_text[:50],
            question_index=self.current_question_index,
        )
        
        # Save to chat history if supabase available
        if supabase and self.user_id:
            try:
                supabase.table("chat_history").insert({
                    "user_id": self.user_id,
                    "role": "user",
                    "content": user_text,
                    "metadata": {
                        "call_type": "topic_call",
                        "topic": self.topic_title,
                        "scheduled_by": self.scheduled_by_name,
                        "turn": self.turn_count,
                    }
                }).execute()
            except Exception as e:
                logger.warning(f"Failed to save chat: {e}")


async def handle_topic_session(ctx: agents.JobContext):
    """
    Handle a topic-based scheduled call.
    
    This is triggered when someone schedules a call with specific questions.
    Uses a completely different persona - soft, caring friend (NOT girlfriend).
    """
    room = ctx.room
    
    # Get user ID from room
    user_id = None
    for participant in room.remote_participants.values():
        user_id = participant.identity
        break
    
    if not user_id:
        room_name = room.name
        if room_name.startswith("synki-topic-"):
            user_id = room_name[12:]  # Remove "synki-topic-" prefix
        elif room_name.startswith("synki-"):
            user_id = room_name[6:]
        else:
            user_id = room_name
    
    logger.info(
        "topic_session_started",
        user_id=user_id,
        room_name=room.name,
    )
    
    # Load topic context from scheduled_calls
    topic_title = "check-in"
    topic_prompts = ["Aap kaise hain aaj?"]
    scheduled_by_name = "Someone"
    relationship = "friend"
    user_name = "Friend"
    
    if supabase:
        try:
            from datetime import datetime as dt
            
            # Get user name
            profile = supabase.table("profiles").select("name").eq("id", user_id).single().execute()
            if profile.data:
                user_name = profile.data.get("name", "Friend")
            
            # FIRST: Check proactive_pending (this is where call UI stores context)
            # Status can be "pending", "accepted", "answered", or "agent_handled"
            pending_call = supabase.table("proactive_pending")\
                .select("id, context")\
                .eq("user_id", user_id)\
                .in_("status", ["pending", "accepted", "answered", "agent_handled"])\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            
            if pending_call.data:
                context = pending_call.data[0].get('context', {})
                if context.get('topic_prompts'):
                    topic_title = context.get('topic_title', 'check-in')
                    topic_prompts = context.get('topic_prompts', ["Aap kaise hain?"])
                    scheduled_by_name = context.get('scheduled_by', 'Someone')
                    relationship = context.get('relationship', 'friend')
                    
                    logger.info(
                        "topic_context_from_proactive_pending",
                        topic=topic_title,
                        prompts=len(topic_prompts),
                        scheduled_by=scheduled_by_name,
                    )
                    
                    # Mark as completed by topic agent
                    supabase.table("proactive_pending")\
                        .update({"status": "topic_completed"})\
                        .eq("id", pending_call.data[0]['id'])\
                        .execute()
            
            # FALLBACK: Check scheduled_calls if no proactive_pending found
            if topic_prompts == ["Aap kaise hain?"]:  # Still default
                scheduled_call = supabase.table("scheduled_calls")\
                    .select("id, metadata, message")\
                    .eq("user_id", user_id)\
                    .eq("status", "triggered")\
                    .order("triggered_at", desc=True)\
                    .limit(1)\
                    .execute()
                
                if scheduled_call.data:
                    call_data = scheduled_call.data[0]
                    metadata = call_data.get('metadata', {})
                    
                    if metadata.get('topic_prompts'):
                        topic_title = metadata.get('topic_title', 'check-in')
                        topic_prompts = metadata.get('topic_prompts', ["Aap kaise hain?"])
                        scheduled_by_name = metadata.get('scheduled_by_name', 'Someone')
                        relationship = metadata.get('relationship', 'friend')
                        
                        logger.info(
                            "topic_context_from_scheduled_calls",
                            topic=topic_title,
                            prompts=len(topic_prompts),
                            scheduled_by=scheduled_by_name,
                        )
                        
                        # Mark as answered
                        supabase.table("scheduled_calls")\
                            .update({"status": "answered", "answered_at": dt.now().isoformat()})\
                            .eq("id", call_data['id'])\
                            .execute()
                    
        except Exception as e:
            logger.warning(f"Failed to load topic context: {e}")
    
    try:
        # Configure STT
        stt_config = deepgram.STT(
            model="nova-3",
            language="multi",
        )
        
        # Configure LLM
        llm_config = openai.LLM(
            model="gpt-4o-mini",
            temperature=0.7,  # Slightly lower for more focused responses
        )
        
        # Configure TTS - use a softer voice
        tts_config = openai.TTS(
            model="tts-1",
            voice="shimmer",  # Softer female voice
        )
        
        # Create session
        agent_session = AgentSession(
            stt=stt_config,
            llm=llm_config,
            tts=tts_config,
            vad=silero.VAD.load(),
        )
        
        # Create the topic caller assistant
        assistant = TopicCallerAssistant(
            user_name=user_name,
            scheduled_by_name=scheduled_by_name,
            topic_title=topic_title,
            topic_prompts=topic_prompts,
            relationship=relationship,
            user_id=user_id,
        )
        
        # Start session
        await agent_session.start(
            room=room,
            agent=assistant,
        )
        
        logger.info(
            "topic_agent_started",
            user_name=user_name,
            topic=topic_title,
            scheduled_by=scheduled_by_name,
        )
        
        # Generate simple, direct greeting - NO girlfriend talk
        first_question = topic_prompts[0] if topic_prompts else "Aap kaise hain?"
        greeting = f"""Say EXACTLY this (don't add anything romantic or girlfriend-like):

"Hello {user_name}, main Synki hoon. {scheduled_by_name} ne mujhe aapse baat karne ke liye bheja. {first_question}"

Just say that. Nothing more. Wait for their answer."""
        
        await agent_session.generate_reply(instructions=greeting)
        
    except Exception as e:
        logger.error(
            "topic_session_error",
            error=str(e),
        )
        raise


# Export the handler for registration in companion_agent.py
__all__ = ["TopicCallerAssistant", "handle_topic_session", "set_supabase_client"]
