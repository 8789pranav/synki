import asyncio
from datetime import datetime
from synki.orchestrator.context_builder import ContextBuilder

async def test():
    cb = ContextBuilder()
    user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'
    
    # Check current date
    date = datetime.now().strftime('%Y-%m-%d')
    print(f'Current date being queried: {date}')
    
    # Call the method
    await cb._load_persisted_questions(user_id)
    
    # Check what was loaded
    print(f'questions_asked loaded: {cb._session_questions_asked.get(user_id, [])}')
    print(f'Loaded from DB set: {cb._loaded_from_db}')

asyncio.run(test())
