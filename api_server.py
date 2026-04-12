"""
Synki API Server

Simple FastAPI server for authentication and token generation.
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

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

# ===== GLOBAL SUPABASE CLIENT (reuse connection pool!) =====
from supabase import create_client as _create_supabase_client
_supabase_client = None

def get_supabase():
    """Get or create global Supabase client (reuses connection pool)."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = _create_supabase_client(
            os.environ.get('SUPABASE_URL'),
            os.environ.get('SUPABASE_SERVICE_KEY')
        )
    return _supabase_client

# Get the directory where api_server.py is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Background scheduler task
scheduler_task = None

async def scheduled_calls_checker():
    """Background task to check and trigger scheduled calls every 30 seconds."""
    logger.info("⏰ Scheduled calls checker started")
    
    while True:
        try:
            # Get pending scheduled calls that are due
            pending_calls = await db_service.get_pending_calls_to_trigger()
            
            if pending_calls:
                logger.info(f"⏰ Found {len(pending_calls)} scheduled calls to trigger")
                
                supabase = get_supabase()  # Use global client!
                
                for call in pending_calls:
                    call_id = call['id']
                    user_id = call['user_id']
                    message = call.get('message') or "Scheduled call time! 💕"
                    call_type = call.get('call_type', 'scheduled')
                    metadata = call.get('metadata', {})
                    
                    # Extract topic info from metadata (for scheduled topic calls)
                    topic_title = metadata.get('topic_title')
                    topic_prompts = metadata.get('topic_prompts', [])
                    scheduled_by = metadata.get('scheduled_by_name')
                    relationship = metadata.get('relationship')
                    is_self_scheduled = metadata.get('is_self_scheduled', False)
                    
                    # Update status to triggered
                    await db_service.update_scheduled_call_status(
                        call_id=call_id,
                        status="triggered",
                        triggered_at=datetime.utcnow().isoformat()
                    )
                    
                    # Build context with topic info if present
                    context = {
                        "scheduled_call_id": call_id, 
                        "call_type": call_type,
                    }
                    if topic_prompts:
                        context["topic_title"] = topic_title
                        context["topic_prompts"] = topic_prompts
                        context["scheduled_by"] = scheduled_by
                        context["relationship"] = relationship
                        context["is_self_scheduled"] = is_self_scheduled
                        logger.info(f"📋 Topic call: {topic_title} with {len(topic_prompts)} questions (self={is_self_scheduled})")
                    
                    # Create proactive_pending entry for the call UI
                    try:
                        supabase.table("proactive_pending").insert({
                            "user_id": user_id,
                            "contact_type": "call",
                            "message": message,
                            "context": context,
                            "status": "pending",
                            "created_at": datetime.utcnow().isoformat(),
                        }).execute()
                        
                        logger.info(f"📞 Triggered scheduled call for user {user_id[:8]}...")
                    except Exception as e:
                        logger.error(f"Failed to create proactive_pending: {e}")
                    
                    # Send push notification to user's devices
                    try:
                        from synki.services.push_service import push_service
                        
                        tokens = await db_service.get_user_push_tokens(user_id)
                        if tokens:
                            for token_info in tokens:
                                await push_service.send_call_notification(
                                    token=token_info['token'],
                                    caller_name="Synki",
                                    message=message,
                                    call_id=call_id
                                )
                            logger.info(f"📲 Sent push notification to {len(tokens)} devices")
                    except Exception as e:
                        logger.error(f"Failed to send push notification: {e}")
            
            # Also check for delegated calls (calls to family members)
            delegated_calls = await db_service.get_pending_delegated_calls()
            
            if delegated_calls:
                logger.info(f"👨‍👩‍👧 Found {len(delegated_calls)} delegated calls to trigger")
                
                for call in delegated_calls:
                    call_id = call['id']
                    owner_id = call['owner_id']
                    linked_user_name = call.get('linked_user_name', 'Family')
                    linked_user_push_token = call.get('linked_user_push_token')
                    topic_title = call.get('topic_title', 'Check-in')
                    topic_prompts = call.get('topic_prompts', [])
                    custom_message = call.get('custom_message') or f"Call from Synki - {topic_title}"
                    
                    # Update status to triggered
                    await db_service.update_delegated_call(
                        call_id=call_id,
                        status='triggered',
                        triggered_at=datetime.utcnow().isoformat()
                    )
                    
                    logger.info(f"📞 Triggering delegated call to {linked_user_name} for owner {owner_id[:8]}...")
                    
                    # Send push notification if linked user has token
                    if linked_user_push_token:
                        try:
                            from synki.services.push_service import push_service
                            
                            await push_service.send_call_notification(
                                token=linked_user_push_token,
                                caller_name="Synki",
                                message=custom_message,
                                call_id=call_id
                            )
                            logger.info(f"📲 Sent push to linked user {linked_user_name}")
                        except Exception as e:
                            logger.error(f"Failed to send push to linked user: {e}")
        
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        
        # Check every 30 seconds
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    global scheduler_task
    
    # Startup: Start the background scheduler
    logger.info("🚀 Starting Synki API Server...")
    scheduler_task = asyncio.create_task(scheduled_calls_checker())
    
    yield
    
    # Shutdown: Cancel the scheduler
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info("👋 Synki API Server shutting down")


# FastAPI app with lifespan
app = FastAPI(
    title="Synki API",
    description="Authentication and data API for Synki Voice Companion",
    version="1.0.0",
    lifespan=lifespan
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
    agent_type: str = "companion"  # "companion" or "topic"
    user_name: Optional[str] = None  # Optional user name for context


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

import asyncio
from concurrent.futures import ThreadPoolExecutor

# Thread pool for blocking operations
_executor = ThreadPoolExecutor(max_workers=4)

async def get_current_user(authorization: str = Header(None)) -> Optional[AuthUser]:
    """Get current user from auth header."""
    if not authorization:
        return None
    
    try:
        token = authorization.replace("Bearer ", "")
        
        # Run blocking Supabase call in thread pool with timeout
        loop = asyncio.get_event_loop()
        try:
            user = await asyncio.wait_for(
                loop.run_in_executor(_executor, auth_service.verify_token_sync, token),
                timeout=5.0  # 5 second timeout
            )
            return user
        except asyncio.TimeoutError:
            logger.warning("Auth verification timed out")
            return None
    except Exception as e:
        logger.warning(f"Auth error: {e}")
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
    livekit_url = os.getenv('LIVEKIT_URL', 'wss://zupki-hv3uw8fv.livekit.cloud')
    
    logger.info(f"🔑 LIVEKIT CONFIG: url={livekit_url}, key={api_key[:8]}...")
    
    if not api_key or not api_secret:
        raise HTTPException(status_code=500, detail="LiveKit not configured")
    
    try:
        # Create LiveKit API client
        lk_api = LiveKitAPI(
            url=livekit_url.replace('wss://', 'https://'),
            api_key=api_key,
            api_secret=api_secret,
        )
        
        # Create room with metadata indicating call type
        # Agent reads this to determine which persona to use
        room_metadata = json.dumps({"call_type": request.agent_type or "companion"})
        
        await lk_api.room.create_room(
            CreateRoomRequest(
                name=request.room_name,
                empty_timeout=300,  # 5 minutes
                metadata=room_metadata,
            )
        )
        logger.info(f"🏠 Room created: {request.room_name} (call_type: {request.agent_type})")
        
        # Build job metadata with topic info for the agent
        # This is the RELIABLE way to pass data to the agent per LiveKit docs
        job_metadata = {
            "call_type": request.agent_type or "companion",
            "user_id": request.user_id,
            "user_name": request.user_name or "Friend",
        }
        
        # If this is a topic call, fetch topic context from proactive_pending
        if request.agent_type == "topic":
            try:
                from supabase import create_client
                sb = create_client(
                    os.environ.get('SUPABASE_URL'),
                    os.environ.get('SUPABASE_SERVICE_KEY')
                )
                topic_context = sb.table("proactive_pending")\
                    .select("context")\
                    .eq("user_id", request.user_id)\
                    .in_("status", ["pending", "accepted", "answered"])\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()
                
                if topic_context.data and topic_context.data[0].get('context'):
                    ctx = topic_context.data[0]['context']
                    job_metadata["topic_title"] = ctx.get("topic_title", "check-in")
                    job_metadata["topic_prompts"] = ctx.get("topic_prompts", [])
                    job_metadata["scheduled_by"] = ctx.get("scheduled_by", "Someone")
                    job_metadata["is_self_scheduled"] = ctx.get("is_self_scheduled", False)
                    logger.info(f"📋 Topic context loaded: {job_metadata['topic_title']}, {len(job_metadata.get('topic_prompts', []))} prompts")
            except Exception as e:
                logger.warning(f"Failed to load topic context: {e}")
        
        # Explicitly dispatch the agent to the room WITH job metadata
        agent_name = "synki-companion"
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                room=request.room_name,
                agent_name=agent_name,
                metadata=json.dumps(job_metadata),  # Pass topic info via job metadata!
            )
        )
        logger.info(f"🤖 Agent dispatched: {dispatch.id} with metadata: {job_metadata.get('call_type')}")
        
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


@app.get("/sessions/{user_id}")
async def get_call_history(user_id: str, limit: int = 20, user: AuthUser = Depends(get_current_user)):
    """Get call/session history for user."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    sessions = await db_service.get_sessions(user_id, limit)
    return {"sessions": sessions}


@app.get("/stats/{user_id}")
async def get_user_stats(user_id: str, user: AuthUser = Depends(get_current_user)):
    """Get user conversation statistics."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    stats = await db_service.get_user_stats(user_id)
    return stats


# ==================== USER MEMORIES ====================

@app.get("/api/memories/{user_id}")
async def get_user_memories(user_id: str, user: AuthUser = Depends(get_current_user)):
    """Get user memories (facts, name, preferences)."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('memories').select('*').eq('user_id', user_id).single().execute()
        
        if result.data:
            return result.data
        
        return {"user_id": user_id, "name": None, "facts": [], "preferences": {}}
    except Exception as e:
        # No memories yet - return empty
        return {"user_id": user_id, "name": None, "facts": [], "preferences": {}}


# ==================== SCHEDULED CALLS ====================

class ScheduleCallRequest(BaseModel):
    scheduled_at: str  # ISO format datetime
    call_type: str = "scheduled"
    message: Optional[str] = None
    topic_id: Optional[str] = None  # UUID of call topic
    topic_title: Optional[str] = None  # Topic name
    topic_prompts: Optional[List[str]] = None  # Questions for agent


# STATIC ROUTES MUST COME BEFORE DYNAMIC {user_id} ROUTES
@app.get("/api/schedule/pending")
async def get_pending_calls():
    """Get pending calls to trigger (for scheduler service). No auth - internal use."""
    calls = await db_service.get_pending_calls_to_trigger()
    return {"pending_calls": calls}


@app.get("/api/schedule/my-scheduled")
async def get_my_scheduled_calls(user: AuthUser = Depends(get_current_user)):
    """Get all scheduled calls - both for self and scheduled for others."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Get calls FOR the user (self calls)
        self_calls = supabase.table('scheduled_calls').select('*').eq(
            'user_id', user.id
        ).in_('status', ['pending', 'scheduled']).order('scheduled_at').execute()
        
        # Get calls scheduled BY the user for others
        # We need to filter by metadata->scheduled_by
        all_pending = supabase.table('scheduled_calls').select('*').in_(
            'status', ['pending', 'scheduled']
        ).order('scheduled_at').execute()
        
        scheduled_by_me = [
            c for c in all_pending.data 
            if c.get('metadata', {}).get('scheduled_by') == user.id and c.get('user_id') != user.id
        ]
        
        # Get target user names for scheduled_by_me calls
        for call in scheduled_by_me:
            target_id = call.get('user_id')
            if target_id:
                try:
                    profile = supabase.table('profiles').select('name').eq('id', target_id).single().execute()
                    call['target_name'] = profile.data.get('name') if profile.data else 'Friend'
                except:
                    call['target_name'] = 'Friend'
        
        return {
            "for_me": self_calls.data,
            "by_me": scheduled_by_me,
            "total": len(self_calls.data) + len(scheduled_by_me)
        }
    except Exception as e:
        logger.error(f"Failed to get my scheduled calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DYNAMIC ROUTES WITH {user_id} - must come after static routes
@app.post("/api/schedule/{user_id}")
async def schedule_call(user_id: str, request: ScheduleCallRequest, user: AuthUser = Depends(get_current_user)):
    """Schedule a call for the user."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Build metadata with topic info if present
    metadata = {}
    if request.topic_id:
        metadata['topic_id'] = request.topic_id
    if request.topic_title:
        metadata['topic_title'] = request.topic_title
    if request.topic_prompts:
        metadata['topic_prompts'] = request.topic_prompts
        # Mark as self-scheduled for topic agent to know
        metadata['scheduled_by_name'] = user.name or 'self'
        metadata['is_self_scheduled'] = True
        logger.info(f"📋 Self-schedule with topic: {request.topic_title}, {len(request.topic_prompts)} prompts")
    
    call_id = await db_service.schedule_call(
        user_id=user_id,
        scheduled_at=request.scheduled_at,
        call_type=request.call_type,
        message=request.message,
        metadata=metadata if metadata else None
    )
    
    if call_id:
        return {"success": True, "call_id": call_id, "scheduled_at": request.scheduled_at}
    raise HTTPException(status_code=500, detail="Failed to schedule call")

@app.get("/api/schedule/{user_id}")
async def get_scheduled_calls(user_id: str, status: str = None, user: AuthUser = Depends(get_current_user)):
    """Get scheduled calls for a user."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    calls = await db_service.get_user_scheduled_calls(user_id, status)
    return {"scheduled_calls": calls}

@app.delete("/api/schedule/{user_id}/{call_id}")
async def cancel_scheduled_call(user_id: str, call_id: str, user: AuthUser = Depends(get_current_user)):
    """Cancel a scheduled call."""
    if not user or user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = await db_service.cancel_scheduled_call(call_id, user_id)
    return {"success": success}

@app.post("/api/schedule/{call_id}/trigger")
async def trigger_scheduled_call(call_id: str):
    """Mark a scheduled call as triggered (for scheduler service). No auth - internal use."""
    from datetime import datetime
    success = await db_service.update_scheduled_call_status(
        call_id=call_id,
        status="triggered",
        triggered_at=datetime.utcnow().isoformat()
    )
    return {"success": success}

@app.post("/api/schedule/{call_id}/answered")
async def mark_call_answered(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Mark a scheduled call as answered."""
    from datetime import datetime
    success = await db_service.update_scheduled_call_status(
        call_id=call_id,
        status="answered",
        answered_at=datetime.utcnow().isoformat()
    )
    return {"success": success}


@app.delete("/api/schedule/cancel/{call_id}")
async def cancel_any_scheduled_call(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Cancel a scheduled call (either for self or scheduled by user for others)."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # First check if call exists and user has permission
        call = supabase.table('scheduled_calls').select('*').eq('id', call_id).single().execute()
        
        if not call.data:
            raise HTTPException(status_code=404, detail="Call not found")
        
        call_data = call.data
        metadata = call_data.get('metadata', {})
        
        # User can cancel if:
        # 1. They are the target user (call is FOR them)
        # 2. They scheduled it (scheduled_by matches their id)
        is_target = call_data.get('user_id') == user.id
        is_scheduler = metadata.get('scheduled_by') == user.id
        
        if not is_target and not is_scheduler:
            raise HTTPException(status_code=403, detail="Not authorized to cancel this call")
        
        # Cancel the call
        supabase.table('scheduled_calls').update({
            'status': 'cancelled'
        }).eq('id', call_id).execute()
        
        return {"success": True, "message": "Call cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel scheduled call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PUSH NOTIFICATIONS (FCM) ====================

class PushTokenRequest(BaseModel):
    token: str
    platform: str = "web"  # 'web', 'android', 'ios'
    device_name: Optional[str] = None
    browser: Optional[str] = None

class SendNotificationRequest(BaseModel):
    title: str
    body: str
    call_style: bool = False
    data: Optional[dict] = None

@app.post("/api/push/register")
async def register_push_token(request: PushTokenRequest, user: AuthUser = Depends(get_current_user)):
    """Register a push notification token for the current user."""
    success = await db_service.save_push_token(
        user_id=user.id,
        token=request.token,
        platform=request.platform,
        device_name=request.device_name,
        browser=request.browser
    )
    return {"success": success}

@app.delete("/api/push/unregister")
async def unregister_push_token(token: str, user: AuthUser = Depends(get_current_user)):
    """Unregister a push notification token."""
    success = await db_service.delete_push_token(user_id=user.id, token=token)
    return {"success": success}

@app.get("/api/push/tokens")
async def get_push_tokens(user: AuthUser = Depends(get_current_user)):
    """Get all registered push tokens for the current user."""
    tokens = await db_service.get_user_push_tokens(user.id)
    return {"tokens": tokens}

@app.post("/api/push/test")
async def test_push_notification(user: AuthUser = Depends(get_current_user)):
    """Send a test push notification to all user's devices."""
    try:
        from synki.services.push_service import push_service
        
        tokens = await db_service.get_user_push_tokens(user.id)
        if not tokens:
            return {"success": False, "error": "No push tokens registered"}
        
        results = {"sent": 0, "failed": 0}
        for token_info in tokens:
            success = await push_service.send_notification(
                token=token_info['token'],
                title="Test from Synki 💕",
                body="Push notifications are working!",
                call_style=False
            )
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1
        
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Test push failed: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/push/send-call/{user_id}")
async def send_call_notification(
    user_id: str, 
    message: str = "Synki is calling you! 💕",
    call_id: Optional[str] = None
):
    """Send a call notification to a specific user (internal use)."""
    try:
        from synki.services.push_service import push_service
        
        tokens = await db_service.get_user_push_tokens(user_id)
        if not tokens:
            logger.warning(f"No push tokens for user {user_id[:8]}...")
            return {"success": False, "error": "No push tokens"}
        
        results = {"sent": 0, "failed": 0}
        for token_info in tokens:
            success = await push_service.send_call_notification(
                token=token_info['token'],
                caller_name="Synki",
                message=message,
                call_id=call_id
            )
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1
        
        logger.info(f"📞 Sent call notification to user {user_id[:8]}... ({results['sent']} sent)")
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"Call notification failed: {e}")
        return {"success": False, "error": str(e)}


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

@app.get("/firebase-messaging-sw.js")
async def serve_firebase_sw():
    """Serve the Firebase messaging service worker."""
    return FileResponse(os.path.join(FRONTEND_DIR, "firebase-messaging-sw.js"), media_type="application/javascript")


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
        
        try:
            # Try to get user profile
            result = db_service.supabase.table('profiles').select('name').eq('id', user_id).execute()
            if result.data:
                user_name = result.data[0].get('name')
            
            # Also try to get name from memories
            if not user_name:
                mem_result = db_service.supabase.table('memories').select('name').eq('user_id', user_id).execute()
                if mem_result.data:
                    user_name = mem_result.data[0].get('name')
        except Exception as e:
            logger.warning(f"Could not fetch user data: {e}")
        
        # Generate the base system prompt
        # NOTE: We don't pass memory_facts anymore - favorites should NOT be in system prompt
        # They are only used in context when user asks for suggestions
        system_prompt = engine.get_system_prompt(
            user_name=user_name,
            user_emotion=EmotionState.NEUTRAL,
            memory_facts=None  # Don't spam favorites!
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


# ==================== LINKED USERS (Family/Care) ====================

@app.get("/api/linked-users/{owner_id}")
async def get_linked_users(owner_id: str, user: AuthUser = Depends(get_current_user)):
    """Get all linked users for an owner."""
    users = await db_service.get_linked_users(owner_id)
    return {"users": users, "count": len(users)}


class CreateLinkedUserRequest(BaseModel):
    name: str
    relationship: str
    phone: Optional[str] = None
    email: Optional[str] = None
    avatar_emoji: str = "👵"
    language_preference: str = "hinglish"
    speaking_pace: str = "normal"
    notes: Optional[str] = None


@app.post("/api/linked-users/{owner_id}")
async def create_linked_user(
    owner_id: str,
    request: CreateLinkedUserRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Create a new linked user (family member)."""
    linked_user = await db_service.create_linked_user(
        owner_id=owner_id,
        name=request.name,
        relationship=request.relationship,
        phone=request.phone,
        email=request.email,
        avatar_emoji=request.avatar_emoji,
        language_preference=request.language_preference,
        speaking_pace=request.speaking_pace,
        notes=request.notes
    )
    
    if linked_user:
        return {"success": True, "user": linked_user}
    raise HTTPException(status_code=500, detail="Failed to create linked user")


@app.put("/api/linked-users/{linked_user_id}")
async def update_linked_user(
    linked_user_id: str,
    request: CreateLinkedUserRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Update a linked user."""
    success = await db_service.update_linked_user(
        linked_user_id=linked_user_id,
        name=request.name,
        relationship=request.relationship,
        phone=request.phone,
        email=request.email,
        avatar_emoji=request.avatar_emoji,
        language_preference=request.language_preference,
        speaking_pace=request.speaking_pace,
        notes=request.notes
    )
    
    return {"success": success}


@app.delete("/api/linked-users/{linked_user_id}")
async def delete_linked_user(linked_user_id: str, user: AuthUser = Depends(get_current_user)):
    """Delete (deactivate) a linked user."""
    success = await db_service.delete_linked_user(linked_user_id)
    return {"success": success}


# ==================== CALL TOPICS ====================

@app.get("/api/call-topics/{owner_id}")
async def get_call_topics(owner_id: str, user: AuthUser = Depends(get_current_user)):
    """Get all call topics (creates presets if none exist)."""
    topics = await db_service.get_call_topics(owner_id)
    
    # If no topics, create preset topics for this user
    if not topics:
        topics = await db_service.create_preset_topics_for_user(owner_id)
        return {"topics": topics, "count": len(topics), "created_presets": True}
    
    return {"topics": topics, "count": len(topics)}


class CreateTopicRequest(BaseModel):
    title: str
    description: Optional[str] = None
    emoji: str = "💬"
    prompts: List[str] = []
    persona_adjustments: Optional[dict] = None
    duration_minutes: int = 5


@app.post("/api/call-topics/{owner_id}")
async def create_call_topic(
    owner_id: str,
    request: CreateTopicRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Create a new call topic."""
    topic = await db_service.create_call_topic(
        owner_id=owner_id,
        title=request.title,
        description=request.description,
        emoji=request.emoji,
        prompts=request.prompts,
        persona_adjustments=request.persona_adjustments,
        duration_minutes=request.duration_minutes
    )
    
    if topic:
        return {"success": True, "topic": topic}
    raise HTTPException(status_code=500, detail="Failed to create topic")


# ==================== DELEGATED CALLS ====================

@app.get("/api/delegated-calls/{owner_id}")
async def get_delegated_calls_route(
    owner_id: str,
    status: Optional[str] = None,
    user: AuthUser = Depends(get_current_user)
):
    """Get delegated calls for an owner."""
    calls = await db_service.get_delegated_calls(owner_id, status)
    return {"calls": calls, "count": len(calls)}


class CreateDelegatedCallRequest(BaseModel):
    linked_user_id: str
    scheduled_at: str  # ISO format
    topic_id: Optional[str] = None
    custom_message: Optional[str] = None


@app.post("/api/delegated-calls/{owner_id}")
async def create_delegated_call(
    owner_id: str,
    request: CreateDelegatedCallRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Schedule a delegated call to a family member."""
    call = await db_service.create_delegated_call(
        owner_id=owner_id,
        linked_user_id=request.linked_user_id,
        scheduled_at=request.scheduled_at,
        topic_id=request.topic_id,
        custom_message=request.custom_message
    )
    
    if call:
        # Get linked user details for response
        linked_user = await db_service.get_linked_user(request.linked_user_id)
        return {
            "success": True,
            "call": call,
            "linked_user": linked_user
        }
    raise HTTPException(status_code=500, detail="Failed to schedule call")


@app.delete("/api/delegated-calls/{call_id}")
async def cancel_delegated_call(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Cancel a delegated call."""
    success = await db_service.update_delegated_call(call_id, status='cancelled')
    return {"success": success}


@app.get("/api/delegated-calls/{call_id}/summary")
async def get_call_summary(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Get summary of a completed delegated call."""
    # This is a simplified implementation - in production, add proper filtering
    return {
        "call_id": call_id,
        "duration_seconds": None,
        "summary": None,
        "status": "unknown"
    }


# ==================== SYNKI CONNECTIONS (Social) ====================

@app.get("/api/connections/my-code")
async def get_my_synki_code(user: AuthUser = Depends(get_current_user)):
    """Get current user's Synki code."""
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('synki_codes').select('code, custom_code').eq(
            'user_id', user.id
        ).single().execute()
        
        if result.data:
            return {
                "code": result.data.get('custom_code') or result.data.get('code'),
                "default_code": result.data.get('code'),
                "custom_code": result.data.get('custom_code')
            }
        
        # Generate code if doesn't exist
        supabase.rpc('generate_synki_code').execute()
        return {"code": None, "message": "Please refresh to get your code"}
    except Exception as e:
        logger.error(f"Failed to get synki code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/connections/find/{code}")
async def find_user_by_code(code: str, user: AuthUser = Depends(get_current_user)):
    """Find a user by their Synki code."""
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.rpc('find_user_by_code', {'search_code': code}).execute()
        
        if result.data and len(result.data) > 0:
            found = result.data[0]
            # Don't return if it's the same user
            if found['user_id'] == user.id:
                return {"found": False, "message": "This is your own code!"}
            
            return {
                "found": True,
                "user": {
                    "id": found['user_id'],
                    "name": found['name'],
                    "avatar_url": found['avatar_url'],
                    "code": found['code']
                }
            }
        
        return {"found": False, "message": "No user found with this code"}
    except Exception as e:
        logger.error(f"Failed to find user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/connections")
async def get_connections(
    status: Optional[str] = None,
    user: AuthUser = Depends(get_current_user)
):
    """Get all connections for current user."""
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.rpc('get_user_connections', {
            'p_user_id': user.id,
            'p_status': status
        }).execute()
        
        connections = result.data or []
        
        # Separate into categories
        accepted = [c for c in connections if c['status'] == 'accepted']
        pending_received = [c for c in connections if c['status'] == 'pending' and not c['is_requester']]
        pending_sent = [c for c in connections if c['status'] == 'pending' and c['is_requester']]
        
        return {
            "connections": accepted,
            "pending_requests": pending_received,
            "sent_requests": pending_sent,
            "total": len(connections)
        }
    except Exception as e:
        logger.error(f"Failed to get connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SendConnectionRequest(BaseModel):
    code: str
    relationship: str = "family"
    nickname: Optional[str] = None


@app.post("/api/connections/request")
async def send_connection_request(
    request: SendConnectionRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Send a connection request to another user."""
    try:
        supabase = get_supabase()  # Use global client!
        
        # First, find the target user by code to get their ID
        target_user_result = supabase.rpc('find_user_by_code', {
            'search_code': request.code
        }).execute()
        
        target_user_id = None
        target_user_name = "Someone"
        if target_user_result.data and len(target_user_result.data) > 0:
            target_user_id = target_user_result.data[0]['user_id']
            target_user_name = target_user_result.data[0].get('name', 'Someone')
        
        # Send the connection request
        result = supabase.rpc('send_connection_request', {
            'p_from_user_id': user.id,
            'p_to_user_code': request.code,
            'p_relationship': request.relationship,
            'p_nickname': request.nickname
        }).execute()
        
        if result.data and len(result.data) > 0:
            response = result.data[0]
            
            # If successful, send push notification to target user
            if response['success'] and target_user_id:
                try:
                    from synki.services.push_service import push_service
                    tokens = await db_service.get_user_push_tokens(target_user_id)
                    
                    sender_name = user.name or "Someone"
                    
                    if tokens:
                        for token_info in tokens:
                            await push_service.send_notification(
                                token=token_info['token'],
                                title=f"🤝 New Connection Request!",
                                body=f"{sender_name} wants to connect with you as {request.relationship}",
                                data={
                                    "type": "connection_request",
                                    "from_user": user.id,
                                    "from_name": sender_name,
                                    "relationship": request.relationship,
                                    "connection_id": response.get('connection_id', '')
                                }
                            )
                        logger.info(f"📲 Sent connection request notification to {target_user_name}")
                except Exception as e:
                    logger.warning(f"Failed to send connection notification: {e}")
            
            return {
                "success": response['success'],
                "message": response['message'],
                "connection_id": response.get('connection_id')
            }
        
        return {"success": False, "message": "Unknown error"}
    except Exception as e:
        logger.error(f"Failed to send request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RespondConnectionRequest(BaseModel):
    accept: bool
    nickname: Optional[str] = None


@app.post("/api/connections/{connection_id}/respond")
async def respond_to_connection(
    connection_id: str,
    request: RespondConnectionRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Accept or reject a connection request."""
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.rpc('respond_to_connection', {
            'p_connection_id': connection_id,
            'p_user_id': user.id,
            'p_accept': request.accept,
            'p_nickname': request.nickname
        }).execute()
        
        if result.data and len(result.data) > 0:
            response = result.data[0]
            return {
                "success": response['success'],
                "message": response['message']
            }
        
        return {"success": False, "message": "Unknown error"}
    except Exception as e:
        logger.error(f"Failed to respond: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/connections/{connection_id}")
async def remove_connection(
    connection_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """Remove a connection."""
    try:
        supabase = get_supabase()  # Use global client!
        
        supabase.table('synki_connections').delete().eq(
            'id', connection_id
        ).execute()
        
        return {"success": True, "message": "Connection removed"}
    except Exception as e:
        logger.error(f"Failed to remove connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== CONNECTION CALL SCHEDULING ====================

class ConnectionCallRequest(BaseModel):
    scheduled_at: str  # ISO format datetime
    message: Optional[str] = None
    topic_id: Optional[str] = None  # UUID of call topic
    topic_prompts: Optional[List[str]] = None  # Questions/prompts for agent


@app.post("/api/connections/{connection_id}/schedule-call")
async def schedule_call_for_connection(
    connection_id: str,
    request: ConnectionCallRequest,
    user: AuthUser = Depends(get_current_user)
):
    """Schedule a call for a connected user (Synki will call them)."""
    try:
        supabase = get_supabase()  # Use global client!
        
        # Verify connection exists and is accepted
        conn_result = supabase.table('synki_connections').select(
            'id, user_id, connected_user_id, status, permissions, relationship'
        ).eq('id', connection_id).single().execute()
        
        if not conn_result.data:
            raise HTTPException(status_code=404, detail="Connection not found")
        
        conn = conn_result.data
        
        # Check user is part of connection
        if conn['user_id'] != user.id and conn['connected_user_id'] != user.id:
            raise HTTPException(status_code=403, detail="Not your connection")
        
        if conn['status'] != 'accepted':
            raise HTTPException(status_code=400, detail="Connection not accepted")
        
        # Check permission
        permissions = conn.get('permissions', {})
        if not permissions.get('can_schedule_calls', True):
            raise HTTPException(status_code=403, detail="Not allowed to schedule calls")
        
        # Get the target user (the other person in the connection)
        target_user_id = conn['connected_user_id'] if conn['user_id'] == user.id else conn['user_id']
        
        # Get target user info
        target_user = supabase.table('profiles').select('name').eq('id', target_user_id).single().execute()
        target_name = target_user.data.get('name', 'Friend') if target_user.data else 'Friend'
        
        # Get scheduler name
        scheduler_name = user.name or 'Someone'
        
        # Get topic details if topic_id provided
        topic_data = None
        if request.topic_id:
            try:
                topic_result = supabase.table('call_topics').select('*').eq('id', request.topic_id).single().execute()
                if topic_result.data:
                    topic_data = topic_result.data
            except Exception as e:
                logger.warning(f"Failed to load topic: {e}")
        
        # Log what we're receiving
        logger.info(f"📋 Scheduling call - topic_id: {request.topic_id}, topic_prompts: {request.topic_prompts}")
        
        # Create scheduled call entry with topic context
        call_data = {
            'user_id': target_user_id,  # Who will receive the call
            'scheduled_at': request.scheduled_at,
            'status': 'pending',  # Valid: pending, triggered, answered, missed, cancelled
            'call_type': 'scheduled',  # Valid: scheduled, proactive, reminder
            'message': request.message or f"{scheduler_name} scheduled a call for you! 💕",
            'metadata': {
                'scheduled_by': user.id,
                'scheduled_by_name': scheduler_name,
                'connection_id': connection_id,
                'relationship': conn.get('relationship', 'friend'),
                'topic_id': request.topic_id,
                'topic_title': topic_data.get('title') if topic_data else (request.message if request.topic_prompts else None),
                'topic_prompts': request.topic_prompts or (topic_data.get('prompts') if topic_data else []),
                'topic_emoji': topic_data.get('emoji') if topic_data else None
            }
        }
        
        logger.info(f"📋 Call metadata: {call_data['metadata']}")
        
        result = supabase.table('scheduled_calls').insert(call_data).execute()
        
        if result.data:
            call_id = result.data[0]['id']
            
            # Send push notification to target user
            try:
                from synki.services.push_service import push_service
                tokens = await db_service.get_user_push_tokens(target_user_id)
                
                if tokens:
                    for token_info in tokens:
                        await push_service.send_notification(
                            token=token_info['token'],
                            title=f"📅 {scheduler_name} scheduled a call",
                            body=request.message or f"Synki will call you at the scheduled time!",
                            data={
                                "type": "scheduled_call",
                                "call_id": call_id,
                                "scheduled_by": scheduler_name,
                                "scheduled_at": request.scheduled_at
                            }
                        )
                    logger.info(f"📲 Sent schedule notification to {target_name}")
            except Exception as e:
                logger.warning(f"Failed to send schedule notification: {e}")
            
            return {
                "success": True, 
                "call_id": call_id,
                "message": f"Call scheduled for {target_name}!",
                "target_user": target_name
            }
        
        return {"success": False, "message": "Failed to schedule call"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to schedule connection call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PRESENCE / ONLINE STATUS ====================

class PresenceUpdate(BaseModel):
    status: str = "online"  # 'online', 'away', 'busy', 'in_call', 'offline'
    activity: Optional[str] = None  # e.g., 'talking_to_synki', 'browsing'


@app.post("/api/presence/update")
async def update_presence(
    request: PresenceUpdate,
    user: AuthUser = Depends(get_current_user)
):
    """Update current user's online status."""
    try:
        supabase = get_supabase()  # Use global client!
        
        # Upsert presence record
        supabase.table('user_presence').upsert({
            'user_id': user.id,
            'status': request.status,
            'activity': request.activity,
            'last_seen': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }, on_conflict='user_id').execute()
        
        return {"success": True, "status": request.status}
    except Exception as e:
        logger.error(f"Failed to update presence: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/presence/me")
async def get_my_presence(user: AuthUser = Depends(get_current_user)):
    """Get current user's presence status."""
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('user_presence').select('*').eq(
            'user_id', user.id
        ).single().execute()
        
        if result.data:
            return result.data
        return {"status": "offline", "last_seen": None}
    except Exception as e:
        return {"status": "unknown", "error": str(e)}


@app.get("/api/presence/connections")
async def get_connections_presence(user: AuthUser = Depends(get_current_user)):
    """Get online status of all connected users."""
    try:
        supabase = get_supabase()  # Use global client!
        
        # Get all accepted connections
        connections = supabase.rpc('get_user_connections', {
            'p_user_id': user.id,
            'p_status': 'accepted'
        }).execute()
        
        if not connections.data:
            return {"presence": []}
        
        # Get user IDs of connected users
        connected_user_ids = [c['other_user_id'] for c in connections.data]
        
        # Get presence for all connected users
        presence_result = supabase.table('user_presence').select(
            'user_id, status, activity, last_seen'
        ).in_('user_id', connected_user_ids).execute()
        
        # Build presence map
        presence_map = {p['user_id']: p for p in (presence_result.data or [])}
        
        # Combine with connection info
        result = []
        for conn in connections.data:
            user_id = conn['other_user_id']
            presence = presence_map.get(user_id, {})
            
            # Check if user is online (last seen within 2 minutes)
            last_seen = presence.get('last_seen')
            is_online = False
            if last_seen:
                from datetime import datetime, timedelta
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                    is_online = (datetime.now(last_seen_dt.tzinfo) - last_seen_dt) < timedelta(minutes=2)
                except:
                    pass
            
            result.append({
                'user_id': user_id,
                'name': conn.get('other_user_name', 'Unknown'),
                'relationship': conn.get('relationship', 'friend'),
                'status': presence.get('status', 'offline') if is_online else 'offline',
                'activity': presence.get('activity') if is_online else None,
                'last_seen': last_seen,
                'is_online': is_online
            })
        
        return {"presence": result}
    except Exception as e:
        logger.error(f"Failed to get connections presence: {e}")
        return {"presence": [], "error": str(e)}


# ==================== AUTO-REPLY SETTINGS ====================

class AutoReplySettings(BaseModel):
    auto_reply_enabled: bool = False
    auto_reply_message: str = "Main abhi busy hoon, please message chhod do"
    auto_reply_voice: str = "sweet"  # 'sweet', 'professional', 'casual'
    auto_reply_when: str = "offline"  # 'busy', 'offline', 'always', 'scheduled'


@app.get("/api/settings/auto-reply")
async def get_auto_reply_settings(user: AuthUser = Depends(get_current_user)):
    """Get user's auto-reply settings."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('user_settings').select('*').eq('user_id', user.id).single().execute()
        
        if result.data:
            return {
                "auto_reply_enabled": result.data.get('auto_reply_enabled', False),
                "auto_reply_message": result.data.get('auto_reply_message', 'Main abhi busy hoon, please message chhod do'),
                "auto_reply_voice": result.data.get('auto_reply_voice', 'sweet'),
                "auto_reply_when": result.data.get('auto_reply_when', 'offline'),
            }
        
        # Return defaults if no settings found
        return {
            "auto_reply_enabled": False,
            "auto_reply_message": "Main abhi busy hoon, please message chhod do",
            "auto_reply_voice": "sweet",
            "auto_reply_when": "offline",
        }
    except Exception as e:
        logger.error(f"Failed to get auto-reply settings: {e}")
        return {
            "auto_reply_enabled": False,
            "auto_reply_message": "Main abhi busy hoon, please message chhod do",
            "auto_reply_voice": "sweet",
            "auto_reply_when": "offline",
        }


@app.put("/api/settings/auto-reply")
async def update_auto_reply_settings(settings: AutoReplySettings, user: AuthUser = Depends(get_current_user)):
    """Update user's auto-reply settings."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.info(f"📱 Attempting to save auto-reply settings for user {user.id[:8]}... (enabled: {settings.auto_reply_enabled})")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Upsert settings
        data = {
            'user_id': user.id,
            'auto_reply_enabled': settings.auto_reply_enabled,
            'auto_reply_message': settings.auto_reply_message or 'Main abhi busy hoon',
            'auto_reply_voice': settings.auto_reply_voice or 'sweet',
            'auto_reply_when': settings.auto_reply_when or 'offline',
            'updated_at': datetime.now().isoformat(),
        }
        
        logger.info(f"📱 Upserting data: {data}")
        
        result = supabase.table('user_settings').upsert(
            data, 
            on_conflict='user_id'
        ).execute()
        
        logger.info(f"📱 ✅ Updated auto-reply settings for user {user.id[:8]}... (enabled: {settings.auto_reply_enabled})")
        logger.info(f"📱 Result: {result.data}")
        
        return {"success": True, "settings": data}
    except Exception as e:
        logger.error(f"❌ Failed to update auto-reply settings: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== P2P DIRECT CALL ====================

class P2PCallRequest(BaseModel):
    target_user_id: str
    connection_id: Optional[str] = None


@app.post("/api/call/direct/{target_user_id}")
async def initiate_direct_call(target_user_id: str, user: AuthUser = Depends(get_current_user)):
    """
    Initiate a direct P2P call to another Synki user.
    If they have auto-reply enabled, caller talks to target's AI secretary.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    logger.info(f"📞 ==== DIRECT CALL INITIATED ====")
    logger.info(f"📞 Caller: {user.id[:8]}... -> Target: {target_user_id[:8]}...")
    
    from livekit.api import AccessToken, VideoGrants, LiveKitAPI, CreateRoomRequest
    from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
    
    api_key = os.getenv('LIVEKIT_API_KEY')
    api_secret = os.getenv('LIVEKIT_API_SECRET')
    livekit_url = os.getenv('LIVEKIT_URL', 'wss://zupki-hv3uw8fv.livekit.cloud')
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Check if users are connected (check both directions)
        try:
            conn1 = supabase.table('synki_connections').select('id').eq('user_id', user.id).eq('connected_user_id', target_user_id).eq('status', 'accepted').execute()
            conn2 = supabase.table('synki_connections').select('id').eq('user_id', target_user_id).eq('connected_user_id', user.id).eq('status', 'accepted').execute()
            
            if not (conn1.data or conn2.data):
                raise HTTPException(status_code=403, detail="You must be connected to call this user")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Connection check failed: {e}, allowing call anyway")
            # Allow call if connection check fails (table might not exist)
        
        # Get target user's info and settings
        target_name = 'Friend'
        try:
            target_profile = supabase.table('profiles').select('name').eq('id', target_user_id).execute()
            if target_profile.data:
                target_name = target_profile.data[0].get('name', 'Friend')
        except Exception as e:
            logger.warning(f"Could not get target profile: {e}")
        
        # Get caller info
        caller_name = 'Someone'
        try:
            caller_profile = supabase.table('profiles').select('name').eq('id', user.id).execute()
            if caller_profile.data:
                caller_name = caller_profile.data[0].get('name', 'Someone')
        except Exception as e:
            logger.warning(f"Could not get caller profile: {e}")
        
        # Check target's auto-reply settings
        auto_reply_enabled = False
        auto_reply_when = 'offline'
        auto_reply_message = 'Main busy hoon'
        try:
            settings_result = supabase.table('user_settings').select('*').eq('user_id', target_user_id).execute()
            logger.info(f"📞 Auto-reply settings for {target_user_id[:8]}...: {settings_result.data}")
            if settings_result.data:
                target_settings = settings_result.data[0]
                auto_reply_enabled = target_settings.get('auto_reply_enabled', False)
                auto_reply_when = target_settings.get('auto_reply_when', 'offline')
                auto_reply_message = target_settings.get('auto_reply_message', 'Main busy hoon')
                logger.info(f"📞 Auto-reply enabled: {auto_reply_enabled}, when: {auto_reply_when}, message: {auto_reply_message[:50]}...")
            else:
                logger.info(f"📞 No auto-reply settings found for {target_user_id[:8]}...")
        except Exception as e:
            logger.warning(f"Could not check auto-reply settings: {e}")
        
        # Check if target is online
        target_online = False
        try:
            presence_result = supabase.table('user_presence').select('status, last_seen').eq('user_id', target_user_id).execute()
            if presence_result.data:
                last_seen = presence_result.data[0].get('last_seen')
                if last_seen:
                    try:
                        last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        target_online = (datetime.now(last_seen_dt.tzinfo) - last_seen_dt).total_seconds() < 120
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Could not check presence: {e}")
            # Assume offline if presence check fails
        
        # Determine if auto-reply should be triggered
        use_auto_reply = False
        if auto_reply_enabled:
            if auto_reply_when == 'always':
                use_auto_reply = True
                logger.info(f"📞 Auto-reply TRIGGERED: always mode")
            elif auto_reply_when == 'offline' and not target_online:
                use_auto_reply = True
                logger.info(f"📞 Auto-reply TRIGGERED: offline mode (target is offline)")
            elif auto_reply_when == 'offline' and target_online:
                logger.info(f"📞 Auto-reply NOT triggered: offline mode but target is ONLINE")
            elif auto_reply_when == 'busy':
                # Check if user is in a call (could check active rooms)
                use_auto_reply = not target_online  # Fallback to offline check
                if use_auto_reply:
                    logger.info(f"📞 Auto-reply TRIGGERED: busy mode")
        else:
            logger.info(f"📞 Auto-reply disabled for {target_name}")
        
        # Create room for the call
        room_name = f"p2p-{user.id[:8]}-{target_user_id[:8]}-{int(datetime.now().timestamp())}"
        
        # Create LiveKit API client
        lk_api = LiveKitAPI(
            url=livekit_url.replace('wss://', 'https://'),
            api_key=api_key,
            api_secret=api_secret,
        )
        
        call_type = 'proxy' if use_auto_reply else 'p2p'
        room_metadata = json.dumps({
            "call_type": call_type,
            "caller_id": user.id,
            "caller_name": caller_name,
            "target_id": target_user_id,
            "target_name": target_name,
        })
        
        await lk_api.room.create_room(
            CreateRoomRequest(
                name=room_name,
                empty_timeout=300,
                metadata=room_metadata,
            )
        )
        
        if use_auto_reply:
            # Dispatch proxy agent to answer on behalf of target
            job_metadata = {
                "call_type": "proxy",
                "caller_id": user.id,
                "caller_name": caller_name,
                "target_id": target_user_id,
                "target_name": target_name,
                "auto_reply_message": auto_reply_message,
            }
            
            dispatch = await lk_api.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="synki-companion",
                    metadata=json.dumps(job_metadata),
                )
            )
            logger.info(f"📞 Auto-reply call: {caller_name} -> {target_name}'s AI secretary")
        else:
            # TODO: Send notification to target user to join call
            # For now, dispatch agent anyway but in "ringing" mode
            logger.info(f"📞 Direct call: {caller_name} -> {target_name} (target is online)")
        
        await lk_api.aclose()
        
        # Create token for caller
        token = AccessToken(api_key, api_secret) \
            .with_identity(user.id) \
            .with_name(caller_name) \
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name
            ))
        
        # Store incoming call for target user (if not auto-reply)
        if not use_auto_reply:
            try:
                # Store in pending_calls table - use UTC time to match check_incoming_calls
                call_created_at = datetime.utcnow().isoformat() + 'Z'
                supabase.table('pending_calls').insert({
                    'id': room_name,
                    'caller_id': user.id,
                    'caller_name': caller_name,
                    'target_id': target_user_id,
                    'room_name': room_name,
                    'status': 'ringing',
                    'created_at': call_created_at
                }).execute()
                logger.info(f"📞 ✅ CALL STORED: {caller_name} -> {target_name}, room={room_name}, created_at={call_created_at}")
                
                # Send push notification to target user
                try:
                    from synki.services.push_service import push_service
                    
                    tokens = await db_service.get_user_push_tokens(target_user_id)
                    if tokens:
                        for token_info in tokens:
                            await push_service.send_call_notification(
                                token=token_info['token'],
                                caller_name=caller_name,
                                message=f"📞 {caller_name} is calling you!",
                                call_id=room_name
                            )
                        logger.info(f"📲 Sent P2P call notification to {target_name} ({len(tokens)} devices)")
                    else:
                        logger.warning(f"📵 No push tokens for {target_name}")
                except Exception as push_err:
                    logger.warning(f"Failed to send P2P call push notification: {push_err}")
                    
            except Exception as e:
                logger.warning(f"Could not store pending call: {e}")
        
        return {
            "success": True,
            "token": token.to_jwt(),
            "room_name": room_name,
            "url": livekit_url,
            "call_type": call_type,
            "target_name": target_name,
            "auto_reply": use_auto_reply,
            "message": f"Calling {target_name}..." if not use_auto_reply else f"{target_name} is unavailable. You're talking to their AI secretary."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initiate P2P call: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ===== INCOMING CALL ENDPOINTS =====

@app.get("/api/calls/incoming")
async def check_incoming_calls(user: AuthUser = Depends(get_current_user)):
    """Check if there are any incoming calls for this user."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Clean up stale calls (older than 90 seconds) - prevents ghost calls
        try:
            from datetime import timedelta
            cutoff = (datetime.utcnow() - timedelta(seconds=90)).isoformat() + 'Z'
            supabase.table('pending_calls').update({'status': 'missed'}).eq('target_id', user.id).eq('status', 'ringing').lt('created_at', cutoff).execute()
        except Exception:
            pass  # Cleanup is best-effort
        
        # Get pending calls for this user
        result = supabase.table('pending_calls').select('*').eq('target_id', user.id).eq('status', 'ringing').order('created_at', desc=True).limit(1).execute()
        
        # Debug logging
        if result.data:
            logger.info(f"📞 Found {len(result.data)} ringing call(s) for user {user.id[:8]}...")
        
        if result.data:
            call = result.data[0]
            # Check if call is still valid (less than 90 seconds old - extended from 60)
            try:
                created = datetime.fromisoformat(call['created_at'].replace('Z', '+00:00'))
                now = datetime.now(created.tzinfo)
                age = (now - created).total_seconds()
                logger.info(f"📞 Call age: {age:.1f}s, caller: {call['caller_name']}")
            except Exception as e:
                age = 0  # If parsing fails, assume valid
                logger.warning(f"📞 Could not parse created_at: {e}")
            
            if age < 90:  # Extended to 90 seconds
                logger.info(f"📞 ✅ Returning incoming call from {call['caller_name']}")
                return {
                    "has_incoming_call": True,
                    "call": {
                        "id": call['id'],
                        "caller_id": call['caller_id'],
                        "caller_name": call['caller_name'],
                        "caller_avatar": "👤",
                        "room_name": call['room_name'],
                        "created_at": call['created_at']
                    }
                }
            else:
                # Mark as missed
                supabase.table('pending_calls').update({'status': 'missed'}).eq('id', call['id']).execute()
        
        return {"has_incoming_call": False, "call": None}
        
    except Exception as e:
        logger.warning(f"Check incoming calls error: {e}")
        return {"has_incoming_call": False, "call": None}


@app.post("/api/calls/accept/{call_id}")
async def accept_incoming_call(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Accept an incoming call and get token to join the room."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from livekit.api import AccessToken, VideoGrants
    
    api_key = os.getenv('LIVEKIT_API_KEY')
    api_secret = os.getenv('LIVEKIT_API_SECRET')
    livekit_url = os.getenv('LIVEKIT_URL', 'wss://zupki-hv3uw8fv.livekit.cloud')
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Get the call
        result = supabase.table('pending_calls').select('*').eq('id', call_id).eq('target_id', user.id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Call not found")
        
        call = result.data[0]
        room_name = call['room_name']
        
        # Mark as answered
        supabase.table('pending_calls').update({
            'status': 'answered',
            'answered_at': datetime.now().isoformat()
        }).eq('id', call_id).execute()
        
        # Get user's name
        user_name = 'Friend'
        try:
            profile = supabase.table('profiles').select('name').eq('id', user.id).execute()
            if profile.data:
                user_name = profile.data[0].get('name', 'Friend')
        except:
            pass
        
        # Create token for callee
        token = AccessToken(api_key, api_secret) \
            .with_identity(user.id) \
            .with_name(user_name) \
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name
            ))
        
        logger.info(f"📞 Call accepted: {call['caller_name']} -> {user_name}")
        
        return {
            "success": True,
            "token": token.to_jwt(),
            "room_name": room_name,
            "url": livekit_url,
            "caller_name": call['caller_name']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Accept call error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/calls/decline/{call_id}")
async def decline_incoming_call(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Decline an incoming call."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Mark as declined
        supabase.table('pending_calls').update({
            'status': 'declined'
        }).eq('id', call_id).eq('target_id', user.id).execute()
        
        logger.info(f"📞 Call declined: {call_id}")
        
        return {"success": True}
        
    except Exception as e:
        logger.warning(f"Decline call error: {e}")
        return {"success": True}


@app.post("/api/calls/cancel/{call_id}")
async def cancel_outgoing_call(call_id: str, user: AuthUser = Depends(get_current_user)):
    """Cancel an outgoing call (caller hung up before callee answered)."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        # Cancel the call (caller is the one who initiated)
        supabase.table('pending_calls').update({
            'status': 'cancelled'
        }).eq('id', call_id).eq('caller_id', user.id).execute()
        
        logger.info(f"📞 Call cancelled by caller: {call_id}")
        
        return {"success": True}
        
    except Exception as e:
        logger.warning(f"Cancel call error: {e}")
        return {"success": True}


@app.get("/api/calls/status/{room_name}")
async def get_call_status(room_name: str, user: AuthUser = Depends(get_current_user)):
    """Check the status of a call (for caller to know if it was answered/declined)."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('pending_calls').select('status').eq('id', room_name).execute()
        
        if result.data:
            return {"status": result.data[0]['status']}
        
        return {"status": "unknown"}
        
    except Exception as e:
        logger.warning(f"Call status check error: {e}")
        return {"status": "unknown"}


@app.get("/api/messages/auto-reply")
async def get_auto_reply_messages(user: AuthUser = Depends(get_current_user)):
    """Get messages left by callers via auto-reply."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        result = supabase.table('auto_reply_messages').select('*').eq('user_id', user.id).order('created_at', desc=True).limit(50).execute()
        
        return {"messages": result.data or [], "unread_count": len([m for m in (result.data or []) if not m.get('is_read')])}
    except Exception as e:
        logger.error(f"Failed to get auto-reply messages: {e}")
        return {"messages": [], "unread_count": 0}


@app.post("/api/messages/auto-reply/{message_id}/read")
async def mark_message_read(message_id: str, user: AuthUser = Depends(get_current_user)):
    """Mark an auto-reply message as read."""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        supabase = get_supabase()  # Use global client!
        
        supabase.table('auto_reply_messages').update({
            'is_read': True,
            'read_at': datetime.now().isoformat()
        }).eq('id', message_id).eq('user_id', user.id).execute()
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to mark message read: {e}")
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
