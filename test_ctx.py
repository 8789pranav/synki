import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv
from synki.orchestrator.context_builder import ContextBuilder

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    cb = ContextBuilder(supabase_client=supabase)
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    ctx = await cb.build_context(user_id, "test", [])
    
    print('=== Context Data ===')
    print(f'recent_conversations: {ctx.recent_conversations}')
    print(f'recent_summaries: {ctx.recent_summaries}')
    print(f'daily_summary keys: {list(ctx.daily_summary.keys()) if ctx.daily_summary else None}')
    print(f'daily_summary full: {ctx.daily_summary}')

asyncio.run(test())
