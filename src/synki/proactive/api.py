"""
Proactive API - Endpoints for proactive GF system

Endpoints:
- GET /api/proactive/pending - Get pending calls/messages for current user
- POST /api/proactive/answer - Answer a pending call/message
- POST /api/proactive/dismiss - Dismiss (miss) a pending contact
- POST /api/proactive/trigger - Manually trigger a proactive check (for testing)
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/proactive", tags=["proactive"])


# ============================================================================
# Request/Response Models
# ============================================================================

class PendingContact(BaseModel):
    id: str
    contact_type: str  # "call" or "message"
    message: str
    context: dict = {}
    created_at: str
    expires_at: Optional[str] = None


class AnswerRequest(BaseModel):
    pending_id: str


class TriggerRequest(BaseModel):
    user_id: str
    force: bool = False


# ============================================================================
# Endpoints
# ============================================================================

async def get_pending_contacts(user_id: str, supabase) -> list[dict]:
    """Get all pending contacts for a user"""
    try:
        result = supabase.table("proactive_pending")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("status", "pending")\
            .order("created_at", desc=True)\
            .execute()
        
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get pending contacts: {e}")
        return []


async def answer_contact(pending_id: str, supabase) -> bool:
    """Mark a pending contact as answered"""
    try:
        supabase.table("proactive_pending")\
            .update({
                "status": "answered",
                "answered_at": datetime.now().isoformat(),
            })\
            .eq("id", pending_id)\
            .execute()
        return True
    except Exception as e:
        logger.error(f"Failed to answer contact: {e}")
        return False


async def dismiss_contact(pending_id: str, supabase) -> bool:
    """Mark a pending contact as missed/dismissed"""
    try:
        supabase.table("proactive_pending")\
            .update({
                "status": "missed",
            })\
            .eq("id", pending_id)\
            .execute()
        return True
    except Exception as e:
        logger.error(f"Failed to dismiss contact: {e}")
        return False


# ============================================================================
# Integration with existing api_server.py
# ============================================================================

def setup_proactive_routes(app, supabase):
    """
    Setup proactive routes on the FastAPI app.
    
    Usage in api_server.py:
        from synki.proactive.api import setup_proactive_routes
        setup_proactive_routes(app, supabase)
    """
    from synki.proactive import ProactiveScheduler, DecisionEngine, ProactiveMessageGenerator
    
    scheduler = ProactiveScheduler(supabase)
    decision_engine = DecisionEngine(supabase)
    message_generator = ProactiveMessageGenerator()
    
    @app.get("/api/proactive/pending")
    async def get_pending(user_id: str):
        """Get pending calls/messages for user"""
        contacts = await get_pending_contacts(user_id, supabase)
        return {
            "pending": contacts,
            "count": len(contacts),
        }
    
    @app.post("/api/proactive/answer")
    async def answer(request: AnswerRequest, user_id: str):
        """Answer a pending call/message"""
        # Get the pending contact
        result = supabase.table("proactive_pending")\
            .select("*")\
            .eq("id", request.pending_id)\
            .eq("user_id", user_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Pending contact not found")
        
        contact = result.data[0]
        success = await answer_contact(request.pending_id, supabase)
        
        if success:
            # Generate call greeting if it's a call
            greeting = None
            if contact["contact_type"] == "call":
                greeting = message_generator.generate_call_greeting(
                    user_id=user_id,
                    context=contact.get("context", {}),
                )
            
            return {
                "success": True,
                "contact_type": contact["contact_type"],
                "message": contact["message"],
                "greeting": greeting,
                "context": contact.get("context", {}),
            }
        
        raise HTTPException(status_code=500, detail="Failed to answer contact")
    
    @app.post("/api/proactive/dismiss")
    async def dismiss(request: AnswerRequest, user_id: str):
        """Dismiss (miss) a pending call/message"""
        success = await dismiss_contact(request.pending_id, supabase)
        return {"success": success}
    
    @app.post("/api/proactive/trigger")
    async def trigger(request: TriggerRequest):
        """Manually trigger proactive check (for testing)"""
        decision = await decision_engine.should_contact(
            user_id=request.user_id,
            force_check=request.force,
        )
        
        if decision.should_contact:
            # Generate message
            message = message_generator.generate_message(
                user_id=request.user_id,
                contact_type=decision.contact_type.value,
                context=decision.context,
            )
            decision.message = message
            
            # Trigger the contact
            success = await scheduler.trigger_contact(request.user_id, decision)
            
            return {
                "triggered": success,
                "contact_type": decision.contact_type.value,
                "message": message,
                "reason": decision.reason,
            }
        
        return {
            "triggered": False,
            "reason": decision.reason,
        }
    
    @app.get("/api/proactive/stats")
    async def get_stats(user_id: str):
        """Get proactive contact stats for user"""
        try:
            # Count today's contacts
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            result = supabase.table("proactive_contacts")\
                .select("contact_type", count="exact")\
                .eq("user_id", user_id)\
                .gte("created_at", today_start.isoformat())\
                .execute()
            
            return {
                "contacts_today": result.count or 0,
                "max_per_day": decision_engine.MAX_CONTACTS_PER_DAY,
            }
        except Exception as e:
            return {"error": str(e)}
    
    logger.info("Proactive routes setup complete")
