"""
Synki API Server

Simple FastAPI server for authentication and token generation.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
import uvicorn

# Load environment
load_dotenv('.env.local')

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from synki.services.auth_service import get_auth_service, AuthUser
from synki.services.database_service import get_database_service, ChatMessage

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize services
auth_service = get_auth_service()
db_service = get_database_service()

# Get the directory where api_server.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# FastAPI app
app = FastAPI(
    title="Synki API",
    description="Authentication and data API for Synki Voice Companion",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== MODELS ====================

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = "Baby"


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    success: bool
    message: str
    user_id: Optional[str] = None
    access_token: Optional[str] = None
    name: Optional[str] = None


class TokenRequest(BaseModel):
    user_id: str
    room_name: str


class TokenResponse(BaseModel):
    token: str
    room_name: str
    url: str


class MemoryResponse(BaseModel):
    name: Optional[str] = None
    facts: Optional[list] = None
    preferences: Optional[dict] = None
    last_mood: Optional[str] = None
    common_topics: Optional[list] = None


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    emotion: Optional[str] = None
    created_at: Optional[str] = None


class SaveChatRequest(BaseModel):
    role: str
    content: str
    emotion: Optional[str] = None


# ==================== AUTH HELPERS ====================

async def get_current_user(authorization: str = Header(None)) -> Optional[AuthUser]:
    """Get current user from auth header."""
    if not authorization:
        return None
    
    try:
        token = authorization.replace("Bearer ", "")
        user = await auth_service.verify_token(token)
        return user
    except:
        return None


# ==================== ROUTES ====================

@app.get("/")
async def root():
    """Health check."""
    return {"status": "ok", "service": "Synki API", "time": datetime.utcnow().isoformat()}


@app.post("/auth/signup", response_model=AuthResponse)
async def sign_up(request: SignUpRequest):
    """Register a new user."""
    user, error = await auth_service.sign_up(
        email=request.email,
        password=request.password,
        name=request.name
    )
    
    if error:
        return AuthResponse(success=False, message=error)
    
    # Auto sign in after signup
    session, _ = await auth_service.sign_in(request.email, request.password)
    
    return AuthResponse(
        success=True,
        message="Account created successfully!",
        user_id=user.id if user else None,
        access_token=session.access_token if session else None,
        name=request.name
    )


@app.post("/auth/signin", response_model=AuthResponse)
async def sign_in(request: SignInRequest):
    """Sign in an existing user."""
    session, error = await auth_service.sign_in(
        email=request.email,
        password=request.password
    )
    
    if error:
        return AuthResponse(success=False, message=error)
    
    # Get user profile
    user = await auth_service.get_user_by_id(session.user_id)
    
    return AuthResponse(
        success=True,
        message="Signed in successfully!",
        user_id=session.user_id,
        access_token=session.access_token,
        name=user.name if user else "Baby"
    )


@app.post("/auth/signout")
async def sign_out(authorization: str = Header(None)):
    """Sign out the current user."""
    if authorization:
        token = authorization.replace("Bearer ", "")
        await auth_service.sign_out(token)
    return {"success": True, "message": "Signed out"}


@app.get("/auth/me")
async def get_me(user: AuthUser = Depends(get_current_user)):
    """Get current user info."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_authenticated": True
    }


@app.post("/token", response_model=TokenResponse)
async def get_livekit_token(request: TokenRequest):
    """Generate LiveKit room token and explicitly dispatch agent."""
    from livekit.api import AccessToken, VideoGrants, LiveKitAPI, CreateRoomRequest
    from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
    
    api_key = os.getenv('LIVEKIT_API_KEY')
    api_secret = os.getenv('LIVEKIT_API_SECRET')
    livekit_url = os.getenv('LIVEKIT_URL', 'wss://synk-wtut6pa9.livekit.cloud')
    
    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LiveKit not configured")
    
    try:
        # Create LiveKit API client
        lk_api = LiveKitAPI(
            url=livekit_url.replace('wss://', 'https://'),
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Create room first
        await lk_api.room.create_room(
            CreateRoomRequest(
                name=request.room_name,
                empty_timeout=300,  # 5 minutes
            )
        )
        logger.info(f"🏠 Room created: {request.room_name}")
        
        # Explicitly dispatch the agent to the room
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                room=request.room_name,
                agent_name="synki-companion",
            )
        )
        logger.info(f"🤖 Agent dispatched: {dispatch.id}")
        
        await lk_api.aclose()
        
    except Exception as e:
        logger.error(f"Room/dispatch error: {e}")
        import traceback
        traceback.print_exc()
    
    # Create token for user
    token = AccessToken(api_key, api_secret) \
        .with_identity(request.user_id) \
        .with_name(f"user-{request.user_id[:8]}") \
        .with_grants(VideoGrants(
            room_join=True,
            room=request.room_name
        ))
    
    return TokenResponse(
        token=token.to_jwt(),
        room_name=request.room_name,
        url=livekit_url
    )


# ==================== MEMORY & CHAT ====================

@app.get("/memories/{user_id}", response_model=MemoryResponse)
async def get_memories(user_id: str, user: AuthUser = Depends(get_current_user)):
    """Get user memories."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    memories = await db_service.get_memories(user_id)
    
    if memories:
        return MemoryResponse(
            name=memories.name,
            facts=memories.facts or [],
            preferences=memories.preferences or {},
            last_mood=memories.last_mood,
            common_topics=memories.common_topics or []
        )
    
    return MemoryResponse(name=None, facts=[], preferences={}, last_mood=None, common_topics=[])


@app.get("/chat/{user_id}")
async def get_chat_history(user_id: str, limit: int = 20, user: AuthUser = Depends(get_current_user)):
    """Get chat history."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    messages = await db_service.get_recent_chat(user_id, limit)
    return {"messages": messages}


@app.post("/chat/{user_id}")
async def save_chat_message(user_id: str, request: SaveChatRequest, user: AuthUser = Depends(get_current_user)):
    """Save a chat message."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    message = ChatMessage(
        user_id=user_id,
        role=request.role,
        content=request.content,
        emotion=request.emotion
    )
    
    success = await db_service.save_chat_message(message)
    return {"success": success}


@app.get("/stats/{user_id}")
async def get_user_stats(user_id: str, user: AuthUser = Depends(get_current_user)):
    """Get user conversation statistics."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    stats = await db_service.get_user_stats(user_id)
    return stats


# ==================== FRONTEND ====================

@app.get("/app")
async def serve_app():
    """Serve the main app page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "app.html"))

@app.get("/login")
async def serve_login():
    """Serve the login page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/test-notification")
async def serve_notification_test():
    """Serve the notification test/debug page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "test_notification.html"))

@app.get("/call.html")
async def serve_call():
    """Serve the incoming call page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "call.html"))

@app.get("/sw.js")
async def serve_service_worker():
    """Serve the service worker."""
    return FileResponse(os.path.join(FRONTEND_DIR, "sw.js"), media_type="application/javascript")


# ==================== AGENT PROMPT VIEWER ====================

@app.get("/api/agent/prompt")
async def get_agent_prompt(user_id: str):
    """Get the current system prompt AND context used by the agent for a user."""
    from synki.orchestrator.persona_engine import PersonaEngine
    from synki.orchestrator.context_builder import ContextBuilder
    from synki.models import PersonaProfile, LanguageStyle, PersonaMode, EmotionState
    
    try:
        # Create persona engine with default profile
        profile = PersonaProfile(
            mode=PersonaMode.GIRLFRIEND,
            language_style=LanguageStyle.HINGLISH,
            tone="soft, caring, slightly playful",
            question_limit=1,
        )
        engine = PersonaEngine(profile)
        
        # Create context builder
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        ctx_builder = ContextBuilder(supabase_client=supabase)
        
        # Get user info from database
        user_name = None
        memory_facts = []
        
        try:
            # Try to get user profile
            result = db_service.supabase.table('profiles').select('name').eq('id', user_id).execute()
            if result.data:
                user_name = result.data[0].get('name')
            
            # Try to get memories
            mem_result = db_service.supabase.table('memories').select('facts').eq('user_id', user_id).execute()
            if mem_result.data and mem_result.data[0].get('facts'):
                raw_facts = mem_result.data[0].get('facts', [])[:5]
                # Convert facts from [{key, value}] to ["key: value"] strings
                for f in raw_facts:
                    if isinstance(f, dict):
                        memory_facts.append(f"{f.get('key', '')}: {f.get('value', '')}")
                    else:
                        memory_facts.append(str(f))
        except Exception as e:
            logger.warning(f"Could not fetch user data: {e}")
        
        # Generate the base system prompt
        system_prompt = engine.get_system_prompt(
            user_name=user_name,
            user_emotion=EmotionState.NEUTRAL,
            memory_facts=memory_facts
        )
        
        # Build the SMART CONTEXT (what actually gets injected)
        context_text = ""
        context_data = {}
        try:
            prompt_context = await ctx_builder.build_context(
                user_id=user_id,
                user_message="[Context preview - no actual message]",
                recent_messages=[],
            )
            context_text = ctx_builder.format_for_prompt(prompt_context)
            context_data = {
                "user_name": prompt_context.user_name,
                "current_mood": prompt_context.current_mood,
                "stress_level": prompt_context.stress_level,
                "time_of_day": prompt_context.time_of_day,
                "time_based_hint": prompt_context.time_based_hint,
                "recent_summaries_count": len(prompt_context.recent_summaries),
                "questions_already_asked": prompt_context.questions_already_asked,
                "conversation_flow": prompt_context.conversation_flow,
                "likes": prompt_context.likes,
                "dislikes": prompt_context.dislikes,
                "behavior_hint": prompt_context.behavior_hint,
                "contextual_suggestion": prompt_context.contextual_suggestion,
                "suggested_follow_ups": prompt_context.suggested_follow_ups,
            }
        except Exception as e:
            logger.warning(f"Could not build context: {e}")
            context_text = f"[Error building context: {e}]"
        
        return {
            "system_prompt": system_prompt,
            "context_injection": context_text,
            "context_data": context_data,
            "user_name": user_name,
            "memory_facts": memory_facts,
            "profile": {
                "mode": profile.mode.value,
                "language_style": profile.language_style.value,
                "tone": profile.tone,
                "question_limit": profile.question_limit
            }
        }
    except Exception as e:
        logger.error(f"Failed to get prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PROACTIVE GF SYSTEM ====================

from synki.proactive import DecisionEngine, ProactiveMessageGenerator, ProactiveScheduler
from synki.proactive.decision_engine import ContactDecision, ContactType

# Initialize proactive components
proactive_engine = DecisionEngine(db_service.supabase if hasattr(db_service, 'supabase') else None)
proactive_generator = ProactiveMessageGenerator()
proactive_scheduler = None  # Initialize lazily

def get_proactive_scheduler():
    global proactive_scheduler
    if proactive_scheduler is None:
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        proactive_scheduler = ProactiveScheduler(supabase)
    return proactive_scheduler


class ProactiveAnswerRequest(BaseModel):
    pending_id: str
    user_id: str


class ProactiveTriggerRequest(BaseModel):
    user_id: str
    contact_type: str = "call"  # "call" or "message"


@app.get("/api/proactive/pending")
async def get_pending_contacts(user_id: str):
    """Get pending proactive contacts for a user."""
    try:
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        if not supabase:
            return {"pending": [], "count": 0}
        
        result = supabase.table("proactive_pending")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("status", "pending")\
            .order("created_at", desc=True)\
            .execute()
        
        return {
            "pending": result.data or [],
            "count": len(result.data) if result.data else 0
        }
    except Exception as e:
        logger.error(f"Failed to get pending contacts: {e}")
        return {"pending": [], "count": 0, "error": str(e)}


@app.post("/api/proactive/answer")
async def answer_proactive_contact(request: ProactiveAnswerRequest):
    """Answer/acknowledge a proactive contact."""
    try:
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Get the contact
        result = supabase.table("proactive_pending")\
            .select("*")\
            .eq("id", request.pending_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        contact = result.data[0]
        
        # Update status
        supabase.table("proactive_pending")\
            .update({
                "status": "answered",
                "answered_at": datetime.now().isoformat()
            })\
            .eq("id", request.pending_id)\
            .execute()
        
        # Generate greeting if it's a call
        greeting = None
        if contact["contact_type"] == "call":
            greeting = proactive_generator.generate_call_greeting(
                user_id=request.user_id,
                context=contact.get("context", {})
            )
        
        return {
            "success": True,
            "contact_type": contact["contact_type"],
            "message": contact["message"],
            "greeting": greeting,
            "context": contact.get("context", {})
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to answer contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/proactive/dismiss")
async def dismiss_proactive_contact(request: ProactiveAnswerRequest):
    """Dismiss/miss a proactive contact."""
    try:
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        if not supabase:
            return {"success": False}
        
        supabase.table("proactive_pending")\
            .update({"status": "missed"})\
            .eq("id", request.pending_id)\
            .execute()
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to dismiss contact: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/proactive/trigger")
async def trigger_proactive_contact(request: ProactiveTriggerRequest):
    """Manually trigger a proactive contact (for testing)."""
    try:
        supabase = db_service.supabase if hasattr(db_service, 'supabase') else None
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")
        
        # Create a contact decision
        contact_type = ContactType.CALL if request.contact_type == "call" else ContactType.MESSAGE
        
        decision = ContactDecision(
            should_contact=True,
            contact_type=contact_type,
            reason="Manual trigger",
            context={
                "window": "manual",
                "user_mood": "neutral",
                "is_first_today": False
            }
        )
        
        # Generate message
        message = proactive_generator.generate_message(
            user_id=request.user_id,
            contact_type=request.contact_type,
            context=decision.context
        )
        decision.message = message
        
        # Create pending record
        scheduler = get_proactive_scheduler()
        success = await scheduler.trigger_contact(request.user_id, decision)
        
        return {
            "success": success,
            "contact_type": request.contact_type,
            "message": message
        }
    except Exception as e:
        logger.error(f"Failed to trigger contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== RUN ====================

# Mount static files AFTER all routes are defined
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
