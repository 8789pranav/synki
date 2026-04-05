"""
Profile Analysis Scheduler

Scheduled tasks for:
1. Weekly deep analysis (Long-term profile updates)
2. Daily short-term cleanup (Prune old data)
3. Conversation summarization

Can be run as:
- Standalone cron job: python -m synki.orchestrator.profile_scheduler
- Called from main agent periodically
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import structlog

from .user_profile import UserProfileService, LongTermProfile

logger = structlog.get_logger(__name__)


class ProfileScheduler:
    """
    Scheduler for profile analysis tasks.
    
    Weekly Analysis:
    - Collects all unanalyzed conversation summaries
    - Runs deep LLM analysis to update long-term profile
    - Marks summaries as analyzed
    
    Daily Cleanup:
    - Prunes old short-term data (> 6 days)
    - Archives conversation summaries
    """
    
    def __init__(
        self,
        profile_service: UserProfileService,
        supabase_client: Any = None,
        openai_client: Any = None,
    ):
        self.profile_service = profile_service
        self._supabase = supabase_client
        self._openai = openai_client
        
        logger.info("ProfileScheduler initialized")
    
    # =========================================================================
    # CONVERSATION SUMMARIZATION
    # =========================================================================
    
    async def summarize_conversation(
        self,
        user_id: str,
        session_id: str,
        conversation_text: str,
    ) -> str:
        """
        Create a summary of a conversation for later analysis.
        
        DESIGN:
        - Called ONCE at session end (not during)
        - Creates 3-5 sentences capturing key points
        - Focuses on: emotions, topics, key events, user state
        - Max ~300 chars to keep weekly analysis efficient
        """
        print("\n" + "🟢"*30)
        print("📝 CONVERSATION SUMMARY (Session End)")
        print("🟢"*30)
        print(f"   User ID: {user_id}")
        print(f"   Session ID: {session_id}")
        print(f"   Conversation Length: {len(conversation_text)} chars")
        
        if not self._openai:
            print("   ❌ No OpenAI client - using truncation fallback")
            return conversation_text[:300]  # Fallback: just truncate
        
        try:
            # Truncate very long conversations (keep first + last parts)
            max_input = 3000  # ~750 tokens
            if len(conversation_text) > max_input:
                # Keep beginning and end (most important parts)
                half = max_input // 2
                conversation_text = (
                    conversation_text[:half] + 
                    "\n...[middle truncated]...\n" + 
                    conversation_text[-half:]
                )
                print(f"   ⚠️ Conversation truncated to {len(conversation_text)} chars")
            
            prompt = f"""Summarize this conversation in 3-5 SHORT sentences (max 300 characters total).

FOCUS ON:
1. User's emotional state (happy, stressed, sad, excited, etc.)
2. Main topics discussed
3. Any important events or facts mentioned
4. What was on user's mind / their concerns
5. How the conversation ended (resolved, ongoing issue, etc.)

FORMAT: Write as a brief narrative, not bullet points.
Example: "User was stressed about work deadline. Boss criticized their project. They felt tired and upset. Talked about weekend plans which cheered them up. Ended feeling better."

CONVERSATION:
{conversation_text}

SUMMARY (max 300 chars):"""
            
            print("\n   📡 Calling LLM for summary...")
            response = await self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You summarize conversations in 3-5 short sentences. Be concise but capture emotional state and key topics."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=150,  # ~300 chars max
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Ensure max length
            if len(summary) > 350:
                summary = summary[:347] + "..."
            
            print(f"\n   ✅ SUMMARY GENERATED → conversation_summaries:")
            print(f"      \"{summary}\"")
            print(f"      Length: {len(summary)} chars")
            
            # Save to database
            if self._supabase:
                await self._save_conversation_summary(
                    user_id=user_id,
                    session_id=session_id,
                    summary=summary,
                    conversation_date=datetime.now().date(),
                )
                print(f"\n   💾 SAVED TO DATABASE: conversation_summaries")
            
            print("🟢"*30 + "\n")
            
            logger.info(
                "conversation_summarized",
                user_id=user_id,
                summary_length=len(summary),
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            print(f"   ❌ ERROR: {e}")
            print("🟢"*30 + "\n")
            return conversation_text[:300]
    
    MAX_SUMMARIES_PER_USER = 7  # Keep only 7 summaries per user
    
    async def _save_conversation_summary(
        self,
        user_id: str,
        session_id: str,
        summary: str,
        conversation_date: datetime,
    ):
        """Save conversation summary to database (max 7 per user)"""
        if not self._supabase:
            return
        
        try:
            # Extract topics and emotions from summary using simple patterns
            topics = []
            emotions = []
            
            # Simple topic extraction
            topic_keywords = ["work", "family", "health", "relationship", "travel", "food", 
                           "stress", "money", "friends", "career", "hobby"]
            summary_lower = summary.lower()
            for keyword in topic_keywords:
                if keyword in summary_lower:
                    topics.append(keyword)
            
            # Simple emotion extraction
            emotion_keywords = ["happy", "sad", "stressed", "excited", "anxious", "tired", 
                              "angry", "calm", "worried", "bored"]
            for keyword in emotion_keywords:
                if keyword in summary_lower:
                    emotions.append(keyword)
            
            data = {
                "user_id": user_id,
                # NOTE: session_id is UUID type in DB, our session IDs are strings
                # Skip session_id - it allows NULL and we don't need FK to sessions table
                "summary": summary,
                "topics": topics,
                "emotions_detected": emotions,
                "conversation_date": str(conversation_date),
                "analyzed_for_profile": False,
            }
            
            self._supabase.table("conversation_summaries").insert(data).execute()
            
            # Enforce max 7 summaries per user (delete oldest if exceeding)
            await self._enforce_summary_limit(user_id)
            
            logger.info(
                "conversation_summary_saved",
                user_id=user_id,
                topics=topics,
            )
            
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
    
    async def _enforce_summary_limit(self, user_id: str):
        """Keep only MAX_SUMMARIES_PER_USER summaries, delete oldest"""
        if not self._supabase:
            return
        
        try:
            # Get all summaries ordered by date
            result = self._supabase.table("conversation_summaries")\
                .select("id, created_at")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            
            if len(result.data) > self.MAX_SUMMARIES_PER_USER:
                # Delete oldest ones (keep first 7)
                to_delete = result.data[self.MAX_SUMMARIES_PER_USER:]
                
                for row in to_delete:
                    self._supabase.table("conversation_summaries")\
                        .delete()\
                        .eq("id", row["id"])\
                        .execute()
                
                print(f"   🗑️ Deleted {len(to_delete)} old summaries (keeping max {self.MAX_SUMMARIES_PER_USER})")
                logger.info(
                    "old_summaries_deleted",
                    user_id=user_id,
                    deleted_count=len(to_delete),
                )
        except Exception as e:
            logger.error(f"Failed to enforce summary limit: {e}")
    
    # =========================================================================
    # WEEKLY LONG-TERM ANALYSIS
    # =========================================================================
    
    async def run_weekly_analysis(self, user_id: str) -> LongTermProfile | None:
        """
        Run weekly deep analysis to update long-term profile.
        
        This should be scheduled to run once a week (e.g., Sunday night).
        """
        logger.info("starting_weekly_analysis", user_id=user_id)
        
        # Get unanalyzed summaries from last 7 days
        summaries = await self._get_unanalyzed_summaries(user_id)
        
        if not summaries:
            logger.info("no_summaries_to_analyze", user_id=user_id)
            return None
        
        logger.info(
            "analyzing_summaries",
            user_id=user_id,
            count=len(summaries),
        )
        
        # Run deep analysis
        summary_texts = [s["summary"] for s in summaries]
        profile = await self.profile_service.run_weekly_analysis(
            user_id=user_id,
            conversation_summaries=summary_texts,
        )
        
        # Mark summaries as analyzed
        summary_ids = [s["id"] for s in summaries]
        await self._mark_summaries_analyzed(summary_ids)
        
        logger.info(
            "weekly_analysis_complete",
            user_id=user_id,
            confidence=profile.confidence_score if profile else 0,
        )
        
        return profile
    
    async def _get_unanalyzed_summaries(self, user_id: str) -> list[dict]:
        """Get summaries not yet analyzed for long-term profile"""
        if not self._supabase:
            return []
        
        try:
            result = self._supabase.rpc(
                "get_weekly_summaries_for_analysis",
                {"p_user_id": user_id}
            ).execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to get summaries: {e}")
            return []
    
    async def _mark_summaries_analyzed(self, summary_ids: list[str]):
        """Mark summaries as analyzed"""
        if not self._supabase or not summary_ids:
            return
        
        try:
            self._supabase.rpc(
                "mark_summaries_analyzed",
                {"p_summary_ids": summary_ids}
            ).execute()
            
        except Exception as e:
            logger.error(f"Failed to mark analyzed: {e}")
    
    # =========================================================================
    # BATCH PROCESSING
    # =========================================================================
    
    async def run_weekly_for_all_users(self):
        """
        Run weekly analysis for all users with recent activity.
        
        This is the main scheduled job to run weekly.
        """
        if not self._supabase:
            logger.warning("No Supabase client - cannot run batch analysis")
            return
        
        try:
            # Get users with recent conversation summaries
            result = self._supabase.table("conversation_summaries").select(
                "user_id"
            ).eq(
                "analyzed_for_profile", False
            ).execute()
            
            if not result.data:
                logger.info("no_users_to_analyze")
                return
            
            # Get unique user IDs
            user_ids = list(set(item["user_id"] for item in result.data))
            
            logger.info(
                "starting_batch_weekly_analysis",
                user_count=len(user_ids),
            )
            
            # Process each user
            for user_id in user_ids:
                try:
                    await self.run_weekly_analysis(user_id)
                    await asyncio.sleep(1)  # Rate limit
                except Exception as e:
                    logger.error(f"Weekly analysis failed for {user_id}: {e}")
            
            logger.info("batch_weekly_analysis_complete")
            
        except Exception as e:
            logger.error(f"Batch analysis failed: {e}")
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def cleanup_old_summaries(self, days_to_keep: int = 30):
        """
        Archive or delete old conversation summaries.
        """
        if not self._supabase:
            return
        
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date()
            
            # Delete old analyzed summaries
            self._supabase.table("conversation_summaries").delete().lt(
                "conversation_date", str(cutoff_date)
            ).eq(
                "analyzed_for_profile", True
            ).execute()
            
            logger.info(
                "old_summaries_cleaned",
                cutoff_date=str(cutoff_date),
            )
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


# ============================================================================
# STANDALONE RUNNER
# ============================================================================

async def main():
    """Run profile analysis as standalone script"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv(".env.local")
    
    # Initialize clients
    try:
        from supabase import create_client
        from openai import AsyncOpenAI
        
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
        openai_client = AsyncOpenAI()
        
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        return
    
    # Create services
    profile_service = UserProfileService(
        supabase_client=supabase,
        llm_client=openai_client,
    )
    
    scheduler = ProfileScheduler(
        profile_service=profile_service,
        supabase_client=supabase,
        openai_client=openai_client,
    )
    
    # Run weekly analysis for all users
    await scheduler.run_weekly_for_all_users()
    
    # Cleanup old summaries
    await scheduler.cleanup_old_summaries(days_to_keep=30)
    
    logger.info("Scheduled tasks complete")


if __name__ == "__main__":
    asyncio.run(main())
