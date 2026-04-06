import asyncio
from synki.services.database_service import DatabaseService

async def test():
    db = DatabaseService()
    data = db.supabase.table('daily_summaries').select('*').eq('user_id','f3fe2091-63a5-4a24-89ba-0788fc4e12e4').limit(3).execute()
    for d in data.data:
        print('Data keys:', list(d.keys()))
        print('Full record:', d)
        print('---')

asyncio.run(test())
