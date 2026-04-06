#!/usr/bin/env python
"""Debug memory issues - Clean version"""
import os
from dotenv import load_dotenv
load_dotenv('.env.local')
from supabase import create_client

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

print("=== SYNKI CODES ===")
result = supabase.table('synki_codes').select('user_id, code, custom_code').execute()
for c in result.data:
    uid = c.get('user_id', '')[:8]
    code = c.get('code', 'N/A')
    custom = c.get('custom_code', None)
    print(f"  {uid}... = {code} (custom: {custom})")

print()
print("=== PROFILES WITHOUT CODES ===")
profiles = supabase.table('profiles').select('id, name').execute()
codes = supabase.table('synki_codes').select('user_id').execute()
code_users = set(c.get('user_id') for c in codes.data)
missing = False
for p in profiles.data:
    if p.get('id') not in code_users:
        print(f"  {p.get('id', '')[:8]}... = {p.get('name')} - NO CODE!")
        missing = True
if not missing:
    print("  All users have codes!")

print()
print("=== TEST FIND USER BY CODE ===")
# Test finding a user
test_code = result.data[0].get('code') if result.data else 'NONE'
print(f"Testing with code: {test_code}")
try:
    find_result = supabase.rpc('find_user_by_code', {'search_code': test_code}).execute()
    print(f"Result: {find_result.data}")
except Exception as e:
    print(f"Error: {e}")
