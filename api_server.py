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
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/login")
async def serve_login():
    """Serve the login page."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


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
