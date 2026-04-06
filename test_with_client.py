import asyncio
from datetime import datetime
from supabase import create_client
import os
from dotenv import load_dotenv
from synki.orchestrator.context_builder import ContextBuilder

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    cb = ContextBuilder(supabase_client=supabase)
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    print(f'supabase client is None: {cb._supabase is None}')
    
    # Force load
    await cb._load_persisted_questions(user_id)
    
    print(f'After loading:')
    print(f'questions: {len(cb._session_questions_asked.get(user_id, []))} items')

asyncio.run(test())
