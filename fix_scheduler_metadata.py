"""Run SQL migration to fix get_pending_calls_to_trigger function."""
import os
from dotenv import load_dotenv
load_dotenv('.env.local')
from supabase import create_client

supabase = create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_KEY'))

# SQL to update the function to include metadata
sql = """
CREATE OR REPLACE FUNCTION get_pending_calls_to_trigger()
RETURNS TABLE (
    id UUID,
    user_id UUID,
    scheduled_at TIMESTAMPTZ,
    call_type TEXT,
    message TEXT,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT sc.id, sc.user_id, sc.scheduled_at, sc.call_type, sc.message, sc.metadata
    FROM scheduled_calls sc
    WHERE sc.status = 'pending'
      AND sc.scheduled_at <= NOW()
    ORDER BY sc.scheduled_at ASC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
"""

print("Running SQL migration to add metadata to get_pending_calls_to_trigger...")
try:
    result = supabase.rpc('exec_sql', {'sql': sql}).execute()
    print("Migration completed!")
except Exception as e:
    print(f"Error: {e}")
    print("\nYou need to run this SQL manually in Supabase SQL Editor:")
    print(sql)
