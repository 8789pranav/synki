#!/usr/bin/env python
"""Debug memory issues"""
import os
from dotenv import load_dotenv
load_dotenv('.env.local')
from supabase import create_client

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

print("=== ALL USERS (profiles) ===")
profiles = supabase.table('profiles').select('id, name, email').execute()
for p in profiles.data:
    uid = p.get('id', '')[:8]
    name = p.get('name', 'N/A')
    email = p.get('email', 'no email')
    print(f"  {uid}... = {name} ({email})")

print()
print("=== MEMORIES TABLE USER IDS ===")
mems = supabase.table('memories').select('user_id, name, facts').execute()
for m in mems.data:
    uid = m.get('user_id', '')[:8]
    name = m.get('name', 'N/A')
    facts = m.get('facts', [])
    print(f"  {uid}... = {name}, facts: {len(facts)}")

print()
print("=== RECENT CHAT USER IDS ===")
chats = supabase.table('chat_history').select('user_id').order('created_at', desc=True).limit(5).execute()
seen = set()
for c in chats.data:
    uid = c.get('user_id', '')
    if uid not in seen:
        seen.add(uid)
        print(f"  {uid[:8]}...")

print()
print("=== CHECKING USER ID MATCH ===")
profile_ids = set(p.get('id') for p in profiles.data)
memory_ids = set(m.get('user_id') for m in mems.data)
chat_ids = set(c.get('user_id') for c in chats.data)

print(f"Profiles: {len(profile_ids)} users")
print(f"Memories: {len(memory_ids)} users")
print(f"Chat users (recent): {len(chat_ids)} users")

print()
print("Users in chat but NOT in memories:")
missing = chat_ids - memory_ids
for uid in missing:
    print(f"  {uid[:8]}... MISSING from memories table!")

print()
print("=== DAILY SUMMARIES (last 3) ===")
result = supabase.table('conversation_summaries').select('*').order('created_at', desc=True).limit(3).execute()
for s in result.data:
    summary = s.get('summary', '') or ''
    print(f"User: {s.get('user_id', '')[:8]}... Date: {s.get('conversation_date')}")
    print(f"  Topics: {s.get('topics', [])}")
    print(f"  Summary: {summary[:80]}...")
    print()
tables = ['memories', 'user_profiles_short_term', 'user_profiles_long_term', 'conversation_summaries']
for table in tables:
    try:
        result = supabase.table(table).select('*', count='exact').execute()
        print(f"{table}: {result.count} rows")
    except Exception as e:
        print(f"{table}: ERROR - {e}")

print("\n=== MEMORIES CONTENT ===")
result = supabase.table('memories').select('user_id, name, facts, preferences').limit(2).execute()
for m in result.data:
    print(f"User {m['user_id'][:8]}:")
    print(f"  Facts: {m.get('facts', [])}")
    print(f"  Preferences: {m.get('preferences', {})}")

print("\n=== SHORT TERM PROFILES ===")
result = supabase.table('user_profiles_short_term').select('user_id, profile_data, dominant_mood').limit(2).execute()
for p in result.data:
    print(f"User {p['user_id'][:8]}:")
    data = p.get('profile_data', {})
    print(f"  Mood: {p.get('dominant_mood')}")
    print(f"  Profile data keys: {list(data.keys()) if data else 'EMPTY'}")

print("\n=== CONVERSATION SUMMARIES (Recent) ===")
result = supabase.table('conversation_summaries').select('user_id, summary, topics, created_at').order('created_at', desc=True).limit(3).execute()
for s in result.data:
    print(f"User {s['user_id'][:8]} @ {s['created_at'][:10]}:")
    summary = s.get('summary', '')[:100]
    print(f"  Summary: {summary}...")
    print(f"  Topics: {s.get('topics', [])}")

print("\n=== RECENT CHAT HISTORY ===")
result = supabase.table('chat_history').select('user_id, role, content, created_at').order('created_at', desc=True).limit(10).execute()
for c in result.data:
    content = c.get('content', '')[:50]
    print(f"[{c['role']}] {content}...")
