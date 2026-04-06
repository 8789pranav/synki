"""Create preset topics for users."""
import os
import asyncio
from dotenv import load_dotenv
load_dotenv('.env.local')

# Add src to path
import sys
sys.path.insert(0, 'src')

from synki.services.database_service import get_database_service

async def main():
    db = get_database_service()
    
    # Create for test user
    user_id = "f3fe2091-63a5-4a24-89ba-0788fc4e12e4"
    
    print(f"Creating preset topics for user {user_id[:8]}...")
    topics = await db.create_preset_topics_for_user(user_id)
    print(f"Created {len(topics)} topics:")
    for t in topics:
        print(f"  {t.get('emoji', '?')} {t.get('title')}: {len(t.get('prompts', []))} prompts")
    
    # Also create for the other user if they exist
    user_id2 = "bfccbfe1-faa0-41ef-adaa-f1586ba9539a"
    print(f"\nCreating preset topics for user {user_id2[:8]}...")
    topics2 = await db.create_preset_topics_for_user(user_id2)
    print(f"Created {len(topics2)} topics")

if __name__ == "__main__":
    asyncio.run(main())
