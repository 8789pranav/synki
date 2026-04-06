"""Analyze all user data for personalization insights"""
from synki.config import settings
from supabase import create_client

supabase = create_client(settings.supabase.url, settings.supabase.service_key)
user_id = 'f3fe2091-63a5-4a24-89ba-0788fc4e12e4'

print('=== AVAILABLE DATA FOR PERSONALIZATION ===')

# 1. Memories
mem = supabase.table('memories').select('*').eq('user_id', user_id).execute()
print(f'\n1. MEMORIES: {len(mem.data)} records')
if mem.data:
    facts = mem.data[0].get("facts", [])
    print(f'   Facts: {facts[:5]}')
    prefs = mem.data[0].get("preferences", {})
    print(f'   Preferences: {prefs}')

# 2. Chat history patterns
chat = supabase.table('chat_history').select('role, content, emotion, created_at').eq('user_id', user_id).order('created_at', desc=True).limit(50).execute()
print(f'\n2. CHAT HISTORY: {len(chat.data)} messages')

# Analyze short responses (irritation signals)
short_responses = [m for m in chat.data if m['role']=='user' and len(m['content']) < 20]
print(f'   Short responses (<20 chars): {len(short_responses)}')
for sr in short_responses[:5]:
    print(f'     "{sr["content"]}"')

# 3. Daily summaries
daily = supabase.table('daily_summaries').select('*').eq('user_id', user_id).execute()
print(f'\n3. DAILY SUMMARIES: {len(daily.data)} records')
if daily.data:
    for d in daily.data[:2]:
        print(f'   Date: {d.get("date")}')
        print(f'   Topics: {d.get("topics_discussed", [])}')
        print(f'   Mood: {d.get("dominant_mood", "")}')
        print(f'   Highlights: {d.get("highlights", [])}')

# 4. Conversation summaries  
convs = supabase.table('conversation_summaries').select('*').eq('user_id', user_id).execute()
print(f'\n4. CONVERSATION SUMMARIES: {len(convs.data)} records')
for c in convs.data[:2]:
    print(f'   Summary: {c.get("summary", "")[:100]}')
    print(f'   Topics: {c.get("topics", [])}')
    print(f'   Emotions: {c.get("emotions_detected", [])}')

# 5. Short-term profile
short_profile = supabase.table('user_profiles_short_term').select('*').eq('user_id', user_id).execute()
print(f'\n5. SHORT-TERM PROFILE: {len(short_profile.data)} records')
if short_profile.data:
    pd = short_profile.data[0].get('profile_data', {})
    print(f'   Data: {pd}')

# 6. Long-term profile
long_profile = supabase.table('user_profiles_long_term').select('*').eq('user_id', user_id).execute()
print(f'\n6. LONG-TERM PROFILE: {len(long_profile.data)} records')
if long_profile.data:
    pd = long_profile.data[0].get('profile_data', {})
    print(f'   Data: {pd}')

# 7. Analyze behavior patterns
print('\n=== BEHAVIOR ANALYSIS ===')

# Find irritation patterns
print('\nIrritation signals:')
irritation_words = ['hmm', 'ok', 'theek', 'haan', 'accha', 'nahi']
for m in chat.data:
    if m['role'] == 'user':
        content_lower = m['content'].lower()
        if any(w in content_lower for w in irritation_words) and len(m['content']) < 30:
            print(f'   "{m["content"]}"')

# Find positive patterns
print('\nPositive responses:')
positive_words = ['bahut', 'maza', 'accha', 'haan', 'sahi', 'thanks', 'love']
for m in chat.data:
    if m['role'] == 'user':
        content_lower = m['content'].lower()
        if any(w in content_lower for w in positive_words) and len(m['content']) > 30:
            print(f'   "{m["content"][:80]}"')
