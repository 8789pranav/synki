"""
Proactive Scheduler - Background job to check and trigger proactive contacts

This can be run:
1. As a cron job (every 15-30 minutes)
2. As a background worker
3. As a periodic task in the API server
"""

import asyncio
from datetime import datetime
from typing import Optional
import structlog

from .decision_engine import DecisionEngine, ContactType, ContactDecision
from .message_generator import ProactiveMessageGenerator

logger = structlog.get_logger(__name__)


class ProactiveScheduler:
    """
    Schedules and triggers proactive contacts.
    
    Usage:
        scheduler = ProactiveScheduler(supabase, push_service)
        
        # Run once (for cron job)
        await scheduler.check_all_users()
        
        # Or run continuously
        await scheduler.run_forever(interval_minutes=15)
    """
    
    def __init__(
        self,
        supabase_client=None,
        push_service=None,  # Will implement later
    ):
        self._supabase = supabase_client
        self._push_service = push_service
        
        self.decision_engine = DecisionEngine(supabase_client)
        self.message_generator = ProactiveMessageGenerator()
        
        logger.info("ProactiveScheduler initialized")
    
    async def check_user(self, user_id: str) -> Optional[ContactDecision]:
        """
        Check if we should contact a specific user.
        
        Returns ContactDecision if we should contact, None otherwise.
        """
        decision = await self.decision_engine.should_contact(user_id)
        
        if decision.should_contact:
            # Generate message
            message = self.message_generator.generate_message(
                user_id=user_id,
                contact_type=decision.contact_type.value,
                context=decision.context,
            )
            decision.message = message
            
            logger.info(
                "Proactive contact decided",
                user_id=user_id[:8],
                contact_type=decision.contact_type.value,
                reason=decision.reason,
            )
        
        return decision if decision.should_contact else None
    
    async def trigger_contact(
        self,
        user_id: str,
        decision: ContactDecision,
    ) -> bool:
        """
        Trigger the actual contact (send push notification).
        
        Args:
            user_id: User's ID
            decision: The contact decision with type and message
            
        Returns:
            True if successfully triggered, False otherwise
        """
        try:
            if decision.contact_type == ContactType.CALL:
                # Trigger incoming call notification
                success = await self._send_call_notification(user_id, decision)
            else:
                # Trigger message notification
                success = await self._send_message_notification(user_id, decision)
            
            if success:
                # Record the contact
                await self.decision_engine.record_contact(
                    user_id=user_id,
                    contact_type=decision.contact_type,
                    message=decision.message,
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to trigger contact: {e}")
            return False
    
    async def check_all_users(self) -> list[dict]:
        """
        Check all active users and trigger contacts where appropriate.
        
        Returns list of users who were contacted.
        """
        if not self._supabase:
            logger.warning("No Supabase client, cannot check users")
            return []
        
        contacted = []
        
        try:
            # Get active users (users with recent activity)
            # Consider "active" as having chatted in the last 7 days
            result = self._supabase.table("chat_history")\
                .select("user_id")\
                .order("created_at", desc=True)\
                .execute()
            
            # Get unique user IDs
            user_ids = list(set(row["user_id"] for row in result.data))
            
            logger.info(f"Checking {len(user_ids)} users for proactive contact")
            
            for user_id in user_ids:
                decision = await self.check_user(user_id)
                
                if decision:
                    success = await self.trigger_contact(user_id, decision)
                    if success:
                        contacted.append({
                            "user_id": user_id,
                            "contact_type": decision.contact_type.value,
                            "message": decision.message,
                        })
            
            logger.info(f"Proactive contacts triggered: {len(contacted)}")
            return contacted
            
        except Exception as e:
            logger.error(f"Failed to check all users: {e}")
            return []
    
    async def run_forever(self, interval_minutes: int = 15):
        """
        Run the scheduler continuously.
        
        Args:
            interval_minutes: Minutes between checks
        """
        logger.info(f"Starting ProactiveScheduler, interval: {interval_minutes} minutes")
        
        while True:
            try:
                # Check scheduled calls first (these are time-sensitive)
                scheduled = await self.check_scheduled_calls()
                if scheduled:
                    logger.info(f"Triggered {len(scheduled)} scheduled calls")
                
                # Then check proactive contacts
                await self.check_all_users()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(interval_minutes * 60)
    
    async def _send_call_notification(self, user_id: str, decision: ContactDecision) -> bool:
        """Send a call-type notification (incoming call UI)"""
        
        # Create pending proactive contact record
        if self._supabase:
            try:
                self._supabase.table("proactive_pending").insert({
                    "user_id": user_id,
                    "contact_type": "call",
                    "message": decision.message,
                    "context": decision.context,
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": datetime.now().isoformat(),  # + 5 minutes
                }).execute()
            except Exception as e:
                logger.error(f"Failed to create pending contact: {e}")
        
        # TODO: Send actual push notification
        # For now, we create the record and frontend will poll
        if self._push_service:
            return await self._push_service.send_call_notification(
                user_id=user_id,
                caller_name="Synki 💕",
                message=decision.message,
            )
        
        logger.info(f"Call notification queued for {user_id[:8]}...")
        return True
    
    async def _send_message_notification(self, user_id: str, decision: ContactDecision) -> bool:
        """Send a message-type notification"""
        
        # Create pending message record
        if self._supabase:
            try:
                self._supabase.table("proactive_pending").insert({
                    "user_id": user_id,
                    "contact_type": "message",
                    "message": decision.message,
                    "context": decision.context,
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                }).execute()
            except Exception as e:
                logger.error(f"Failed to create pending message: {e}")
        
        # TODO: Send actual push notification
        if self._push_service:
            return await self._push_service.send_message_notification(
                user_id=user_id,
                sender_name="Synki 💕",
                message=decision.message,
            )
        
        logger.info(f"Message notification queued for {user_id[:8]}...")
        return True

    async def check_scheduled_calls(self) -> list[dict]:
        """
        Check for scheduled calls that should be triggered now.
        
        Returns list of calls that were triggered.
        """
        if not self._supabase:
            logger.warning("No Supabase client, cannot check scheduled calls")
            return []
        
        triggered = []
        
        try:
            # Get pending calls that should be triggered
            result = self._supabase.rpc('get_pending_calls_to_trigger').execute()
            
            if not result.data:
                return []
            
            logger.info(f"Found {len(result.data)} scheduled calls to trigger")
            
            for call in result.data:
                call_id = call['id']
                user_id = call['user_id']
                message = call.get('message') or "Scheduled call time! 💕"
                call_type = call.get('call_type', 'scheduled')
                
                # Update status to triggered
                self._supabase.table('scheduled_calls').update({
                    'status': 'triggered',
                    'triggered_at': datetime.now().isoformat()
                }).eq('id', call_id).execute()
                
                # Create pending proactive contact for the incoming call UI
                try:
                    self._supabase.table("proactive_pending").insert({
                        "user_id": user_id,
                        "contact_type": "call",
                        "message": message,
                        "context": {"scheduled_call_id": call_id, "call_type": call_type},
                        "status": "pending",
                        "created_at": datetime.now().isoformat(),
                    }).execute()
                    
                    triggered.append({
                        "call_id": call_id,
                        "user_id": user_id,
                        "message": message,
                        "call_type": call_type,
                    })
                    
                    logger.info(f"⏰ Triggered scheduled call {call_id[:8]}... for user {user_id[:8]}...")
                    
                except Exception as e:
                    logger.error(f"Failed to create pending contact for scheduled call: {e}")
            
            return triggered
            
        except Exception as e:
            logger.error(f"Failed to check scheduled calls: {e}")
            return []


# ============================================================================
# CLI Entry Point (for running as cron job)
# ============================================================================

async def run_scheduler_once():
    """Run the scheduler once (for cron job)"""
    from supabase import create_client
    import os
    
    # Load env
    env_vars = {}
    env_file = ".env.local" if os.path.exists(".env.local") else ".env"
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
    
    supabase = create_client(
        env_vars.get('SUPABASE_URL', os.getenv('SUPABASE_URL')),
        env_vars.get('SUPABASE_SERVICE_KEY', os.getenv('SUPABASE_SERVICE_KEY')),
    )
    
    scheduler = ProactiveScheduler(supabase)
    
    # Check scheduled calls first
    scheduled = await scheduler.check_scheduled_calls()
    print(f"⏰ Scheduled calls triggered: {len(scheduled)}")
    for s in scheduled:
        print(f"   - {s['call_type']}: {s['message'][:50]}...")
    
    # Then check proactive contacts
    contacts = await scheduler.check_all_users()
    
    print(f"✅ Proactive contacts triggered: {len(contacts)}")
    for c in contacts:
        print(f"   - {c['contact_type']}: {c['message'][:50]}...")


if __name__ == "__main__":
    asyncio.run(run_scheduler_once())
