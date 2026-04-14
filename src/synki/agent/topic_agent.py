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
    
    Can be used as:
    1. Helper mode (scheduled by someone else) - professional, focused
    2. Girlfriend mode (self-scheduled) - warm, caring, but focused on topic
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
        is_self_scheduled: bool = False,
    ):
        self.user_name = user_name
        self.scheduled_by_name = scheduled_by_name
        self.topic_title = topic_title
        self.topic_prompts = topic_prompts or ["How are you feeling today?"]
        self.relationship = relationship
        self.user_id = user_id
        self.is_self_scheduled = is_self_scheduled
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
            is_self_scheduled=self.is_self_scheduled,
        )
    
    def _build_instructions(self) -> str:
        """Build instructions using Devanagari Hindi for better TTS pronunciation."""
        
        # Format questions for the prompt
        questions_text = "\n".join([f"   {i+1}. {q}" for i, q in enumerate(self.topic_prompts)])
        
        is_self = self.is_self_scheduled
        
        if is_self:
            # Self-scheduled - sweet friend in Devanagari Hindi
            instructions = f"""तुम Synki हो - {self.user_name} की sweet caring friend।

Context: {self.user_name} ने खुद call schedule की है "{self.topic_title}" के बारे में बात करने।

Topics पूछने हैं:
{questions_text}

🗣️ बोलने का तरीका (बहुत IMPORTANT!):
- Natural pauses डालो: "..." सोचने के लिए
- Fillers use करो: "hmm", "अच्छा", "तो", "like"
- Emotionally react करो: "अरे!", "वाह!", "सच में?!"
- Simple Hindi में बोलो
- Sentences SHORT रखो (5-10 words max)
- Real girl की तरह sound करो

💬 Example natural speech:
- "हेय {self.user_name}!... कैसे हो?"
- "अच्छा अच्छा... hmm... बताओ ना"
- "अरे really?... that's nice!"
- "hmm... समझ गई..."
- "अरे वाह!... और बताओ"
- "ओके ओके... ठीक है!"

📏 Rules:
- ONE question at a time
- Wait... फिर next पूछो
- पहले REACT करो... फिर respond
- SHORT और natural रखो

End: "ओके {self.user_name}... nice talking! Take care... bye!"

Natural रहो... जैसे friend से chatting!"""
        else:
            # Helper mode - professional but natural Hindi
            instructions = f"""तुम Synki हो - {self.user_name} को call करने वाली helpful assistant।

Context: {self.scheduled_by_name} ने तुम्हें भेजा है {self.user_name} से "{self.topic_title}" के बारे में बात करने।

Questions पूछने हैं:
{questions_text}

🗣️ बोलने का तरीका:
- Natural pauses: "..." thinking के लिए  
- Fillers: "hmm", "अच्छा", "ओके"
- Genuinely react करो: "अच्छा", "ओह", "nice"
- Simple Hindi में बोलो
- Sentences SHORT रखो

💬 Example speech:
- "हेलो {self.user_name}!... मैं Synki हूं..."
- "{self.scheduled_by_name} ने... मुझे भेजा है"
- "अच्छा अच्छा... hmm... ओके"
- "ठीक है... समझ गई"

📏 Rules:
- ONE question at a time
- पहले react... फिर next question
- SHORT रखो

End: "ओके... मैं {self.scheduled_by_name} को बता दूंगी... bye!"

Helpful और natural रहो!"""
        
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


async def handle_topic_session(ctx: agents.JobContext, job_metadata: dict = None):
    """
    Handle a topic-based scheduled call.
    
    This is triggered when someone schedules a call with specific questions.
    Uses a completely different persona - soft, caring friend (NOT girlfriend).
    
    Args:
        ctx: LiveKit JobContext
        job_metadata: Optional dict containing topic info passed from dispatch
    """
    room = ctx.room
    job_metadata = job_metadata or {}
    
    # Get user ID from job metadata first, then room
    user_id = job_metadata.get('user_id')
    if not user_id:
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
        has_job_metadata=bool(job_metadata),
    )
    
    # Load topic context - BEST: from job_metadata, FALLBACK: from database
    topic_title = "check-in"
    topic_prompts = ["Aap kaise hain aaj?"]
    scheduled_by_name = "Someone"
    relationship = "friend"
    user_name = job_metadata.get('user_name', 'Friend')
    is_self_scheduled = False
    
    # FIRST: Try to get topic info from job metadata (passed during dispatch)
    # This is the most reliable method per LiveKit docs
    if job_metadata.get('topic_prompts'):
        topic_title = job_metadata.get('topic_title', 'check-in')
        topic_prompts = job_metadata.get('topic_prompts', ["Aap kaise hain?"])
        scheduled_by_name = job_metadata.get('scheduled_by', 'Someone')
        is_self_scheduled = job_metadata.get('is_self_scheduled', False)
        
        logger.info(
            "topic_context_from_job_metadata",
            topic=topic_title,
            prompts=len(topic_prompts),
            scheduled_by=scheduled_by_name,
            is_self=is_self_scheduled,
        )
    elif supabase:
        # FALLBACK: Load from database
        try:
            from datetime import datetime as dt
            
            # Get user name
            profile = supabase.table("profiles").select("name").eq("id", user_id).single().execute()
            if profile.data:
                user_name = profile.data.get("name", "Friend")
            
            # Check proactive_pending (this is where call UI stores context)
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
                    is_self_scheduled = context.get('is_self_scheduled', False)
                    
                    logger.info(
                        "topic_context_from_proactive_pending",
                        topic=topic_title,
                        prompts=len(topic_prompts),
                        scheduled_by=scheduled_by_name,
                        is_self=is_self_scheduled,
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
                        is_self_scheduled = metadata.get('is_self_scheduled', False)
                        
                        logger.info(
                            "topic_context_from_scheduled_calls",
                            topic=topic_title,
                            prompts=len(topic_prompts),
                            scheduled_by=scheduled_by_name,
                            is_self=is_self_scheduled,
                        )
                        
                        # Mark as answered
                        supabase.table("scheduled_calls")\
                            .update({"status": "answered", "answered_at": dt.now().isoformat()})\
                            .eq("id", call_data['id'])\
                            .execute()
                    
        except Exception as e:
            logger.warning(f"Failed to load topic context: {e}")
    
    try:
        # Configure STT - OPTIMIZED for low latency
        stt_config = deepgram.STT(
            model="nova-3",
            language="multi",
            interim_results=True,
            no_delay=True,
            endpointing_ms=25,
        )
        
        # Configure LLM
        llm_config = openai.LLM(
            model="gpt-4o-mini",
            temperature=0.85,  # Higher for more natural, conversational responses
        )
        
        # Configure TTS - Use OpenAI TTS HD (higher quality)
        # 'nova' voice is warm and friendly
        tts_config = openai.TTS(
            model="tts-1-hd",  # HD model for better pronunciation
            voice="nova",  # Warm female voice
        )
        
        logger.info(f"🎭 Topic agent mode: {'self' if is_self_scheduled else 'helper'}, tts: openai-nova-hd")
        
        # Import preloaded VAD from companion_agent for faster startup
        from .companion_agent import PRELOADED_VAD
        
        # Create session with pre-warmed VAD
        agent_session = AgentSession(
            stt=stt_config,
            llm=llm_config,
            tts=tts_config,
            vad=PRELOADED_VAD,  # Use pre-warmed VAD!
        )
        
        # Create the topic caller assistant
        assistant = TopicCallerAssistant(
            user_name=user_name,
            scheduled_by_name=scheduled_by_name,
            topic_title=topic_title,
            topic_prompts=topic_prompts,
            relationship=relationship,
            user_id=user_id,
            is_self_scheduled=is_self_scheduled,
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
            is_self_scheduled=is_self_scheduled,
        )
        
        # Generate greeting in Devanagari Hindi for better pronunciation
        first_question = topic_prompts[0] if topic_prompts else "कैसे हो आप?"
        
        if is_self_scheduled:
            # Self mode - sweet friend greeting in Hindi
            greeting_text = f"हेय {user_name}!... कैसे हो?... तो बताओ ना... {first_question}"
        else:
            # Helper mode - warm greeting in Hindi
            greeting_text = f"हेलो {user_name}!... मैं Synki हूं... {scheduled_by_name} ने मुझे भेजा। तो... {first_question}"
        
        await agent_session.say(greeting_text, allow_interruptions=True)
        
    except Exception as e:
        logger.error(
            "topic_session_error",
            error=str(e),
        )
        raise


# Export the handler for registration in companion_agent.py
__all__ = ["TopicCallerAssistant", "handle_topic_session", "set_supabase_client"]
