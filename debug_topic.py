"""Debug script to check topic data in database."""
import os
from dotenv import load_dotenv
load_dotenv('.env.local')
from supabase import create_client

supabase = create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_KEY'))

# Check chat_history
print('=== CHAT_HISTORY (last 10) ===')
chats = supabase.table('chat_history').select('user_id, role, content, created_at').order('created_at', desc=True).limit(10).execute()
for r in chats.data:
    content = (r.get('content') or 'EMPTY')[:50]
    role = r.get('role', '?')
    print(f"  {role}: {content}")

print()

# Check call_topics
print('=== CALL_TOPICS ===')
topics = supabase.table('call_topics').select('*').execute()
for t in topics.data[:5]:
    prompts = t.get('prompts', [])
    print(f"  {t.get('emoji', '?')} {t.get('title', 'Unknown')}: {len(prompts)} prompts")

if not topics.data:
    print("  NO TOPICS FOUND!")

print()

# Check scheduled_calls with topic_prompts
print('=== SCHEDULED_CALLS (last 3) ===')
result = supabase.table('scheduled_calls').select('id, user_id, status, metadata, message, scheduled_at').order('created_at', desc=True).limit(3).execute()
for r in result.data:
    meta = r.get('metadata', {})
    prompts = meta.get('topic_prompts', [])
    print(f"  Status: {r['status']}, Topic: {meta.get('topic_title')}, Prompts: {len(prompts)}")

print()

# Check proactive_pending
print('=== PROACTIVE_PENDING (last 3) ===')
result2 = supabase.table('proactive_pending').select('id, user_id, status, context, contact_type').order('created_at', desc=True).limit(3).execute()
for r in result2.data:
    ctx = r.get('context', {})
    prompts = ctx.get('topic_prompts', [])
    print(f"  Status: {r['status']}, Type: {r['contact_type']}, Prompts: {len(prompts)}")
