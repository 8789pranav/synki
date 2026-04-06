import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    # Check daily_summaries - ALL data
    result = supabase.table('daily_summaries').select('*').eq('user_id', user_id).order('date', desc=True).limit(5).execute()
    
    print('=== ALL daily_summaries ===')
    for r in result.data:
        print(f"Date: {r.get('date')}")
        print(f"Topics: {r.get('topics_discussed')}")
        print(f"Highlights: {r.get('highlights')}")
        print(f"Concerns: {r.get('concerns')}")
        print(f"Ended on: {r.get('conversation_ended_on')}")
        print(f"Questions count: {len(r.get('questions_asked', []))}")
        # Show last 3 questions
        questions = r.get('questions_asked', [])[-3:]
        for q in questions:
            print(f"  Q: {q[:80]}...")
        print('---')

asyncio.run(test())
