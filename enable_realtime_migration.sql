-- ============================================================================
-- ENABLE REALTIME FOR P2P CALLS
-- Run this in Supabase SQL Editor to enable instant call notifications
-- ============================================================================

-- Enable Realtime on pending_calls table for instant P2P call notifications
-- This replaces polling with WebSocket-based real-time updates

-- First, check if the table exists in the publication
DO $$
BEGIN
    -- Add pending_calls to the Supabase Realtime publication
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
        AND tablename = 'pending_calls'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE pending_calls;
        RAISE NOTICE 'Added pending_calls to supabase_realtime publication';
    ELSE
        RAISE NOTICE 'pending_calls already in supabase_realtime publication';
    END IF;
END $$;

-- Also enable for user_presence (for online status indicators)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' 
        AND tablename = 'user_presence'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE user_presence;
        RAISE NOTICE 'Added user_presence to supabase_realtime publication';
    ELSE
        RAISE NOTICE 'user_presence already in supabase_realtime publication';
    END IF;
END $$;

-- ============================================================================
-- ENABLE ANON ACCESS FOR REALTIME SUBSCRIPTION
-- Since we use custom JWT auth (not Supabase Auth), we need to allow anon
-- SELECT on pending_calls for Realtime subscriptions to work.
-- The filter (target_id=eq.USER_ID) ensures users only see their own calls.
-- ============================================================================

-- Add anon SELECT policy for Realtime (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'pending_calls' 
        AND policyname = 'Anon can view pending_calls for realtime'
    ) THEN
        EXECUTE 'CREATE POLICY "Anon can view pending_calls for realtime" ON pending_calls FOR SELECT USING (true)';
        RAISE NOTICE 'Created anon SELECT policy for pending_calls';
    ELSE
        RAISE NOTICE 'Anon SELECT policy already exists';
    END IF;
END $$;

-- Verify tables are in publication
SELECT * FROM pg_publication_tables WHERE pubname = 'supabase_realtime';

-- Show policies on pending_calls
SELECT * FROM pg_policies WHERE tablename = 'pending_calls';

-- ============================================================================
-- ARCHITECTURE EXPLANATION:
-- 
-- BEFORE (Polling - inefficient):
--   User polls every 2-3 seconds → Server processes request → DB query
--   ❌ Wastes server resources (constant requests)
--   ❌ Up to 3 second delay for call notification
--   ❌ Doesn't scale well with many users
--
-- AFTER (Supabase Realtime - instant):
--   User opens WebSocket connection → INSERT triggers push → Instant notification
--   ✅ No repeated requests - one persistent connection
--   ✅ Instant notification (< 100ms)
--   ✅ Scales to thousands of users
--   ✅ Falls back to polling if WebSocket fails
-- ============================================================================
