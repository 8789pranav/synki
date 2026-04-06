from synki.config import settings
from supabase import create_client
from datetime import datetime, timedelta

supabase = create_client(settings.supabase.url, settings.supabase.service_key)
user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'

# Check chat_history
three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
result = supabase.table('chat_history').select('role, content, created_at').eq('user_id', user_id).gte('created_at', three_days_ago).order('created_at', desc=True).limit(15).execute()

print(f'Found {len(result.data)} messages in chat_history (last 3 days):')
for msg in result.data[:8]:
    print(f"  [{msg['created_at'][:16]}] {msg['role']}: {msg['content'][:50]}...")

# Check conversation_summaries
result2 = supabase.table('conversation_summaries').select('*').eq('user_id', user_id).execute()
print(f"\nFound {len(result2.data)} conversation_summaries")
