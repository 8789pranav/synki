import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    # Check chat_history for recent messages
    result = supabase.table('chat_history').select('role, content, created_at').eq('user_id', user_id).order('created_at', desc=True).limit(10).execute()
    
    print('=== Recent Chat Messages ===')
    for r in result.data:
        role = r.get('role')
        content = r.get('content', '')[:60]
        print(f"{role}: {content}...")

asyncio.run(test())
