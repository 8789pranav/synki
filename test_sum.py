import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    # Check daily_summaries - what columns do we have?
    result = supabase.table('daily_summaries').select('*').eq('user_id', user_id).order('date', desc=True).limit(3).execute()
    
    print('=== daily_summaries ===')
    for r in result.data:
        print(f"Date: {r.get('date')}")
        print(f"Topics: {r.get('topics_discussed')}")
        print(f"Highlights: {r.get('highlights')}")
        print(f"Activities: {r.get('activities')}")
        print(f"Concerns: {r.get('concerns')}")
        print(f"Last topic: {r.get('last_topic')}")
        print(f"Ended on: {r.get('conversation_ended_on')}")
        print('---')

asyncio.run(test())
