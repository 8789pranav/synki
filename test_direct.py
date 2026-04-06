import asyncio
from datetime import datetime
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env.local')

async def test():
    supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    date = datetime.now().strftime('%Y-%m-%d')
    
    print(f'Querying date: {date}')
    
    result = supabase.table('daily_summaries').select('date, questions_asked').eq('user_id', user_id).eq('date', date).execute()
    
    print(f'Result data: {result.data}')
    
    if result.data:
        print(f'Found! Questions: {len(result.data[0].get("questions_asked", []))} items')
    else:
        print('NO DATA FOUND for today!')
        # Try fetching ALL dates for this user to see what's there
        all_data = supabase.table('daily_summaries').select('date').eq('user_id', user_id).execute()
        print(f'Available dates: {[d["date"] for d in all_data.data]}')

asyncio.run(test())
