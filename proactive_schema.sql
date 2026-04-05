-- Proactive GF System - Database Tables
-- Run this in Supabase SQL Editor

-- ============================================================================
-- Table: proactive_contacts (History of proactive contacts)
-- ============================================================================
CREATE TABLE IF NOT EXISTS proactive_contacts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('call', 'message')),
    message TEXT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_proactive_contacts_user_date 
    ON proactive_contacts(user_id, created_at DESC);

-- ============================================================================
-- Table: proactive_pending (Pending contacts waiting for user response)
-- ============================================================================
CREATE TABLE IF NOT EXISTS proactive_pending (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('call', 'message')),
    message TEXT,
    context JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'missed', 'read')),
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT (now() + interval '5 minutes'),
    answered_at TIMESTAMPTZ
);

-- Index for fast pending lookups
CREATE INDEX IF NOT EXISTS idx_proactive_pending_user_status 
    ON proactive_pending(user_id, status, created_at DESC);

-- ============================================================================
-- RLS Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE proactive_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE proactive_pending ENABLE ROW LEVEL SECURITY;

-- Users can only see their own proactive contacts
CREATE POLICY "Users can view own proactive contacts"
    ON proactive_contacts FOR SELECT
    USING (auth.uid() = user_id);

-- Users can view their own pending contacts
CREATE POLICY "Users can view own pending contacts"
    ON proactive_pending FOR SELECT
    USING (auth.uid() = user_id);

-- Users can update status of their pending contacts
CREATE POLICY "Users can update own pending contacts"
    ON proactive_pending FOR UPDATE
    USING (auth.uid() = user_id);

-- Service role can do everything (for backend scheduler)
CREATE POLICY "Service role full access contacts"
    ON proactive_contacts FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access pending"
    ON proactive_pending FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================================================
-- Function to clean up expired pending contacts
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_expired_pending()
RETURNS void AS $$
BEGIN
    UPDATE proactive_pending 
    SET status = 'missed'
    WHERE status = 'pending' 
    AND expires_at < now();
END;
$$ LANGUAGE plpgsql;

-- Optional: Schedule cleanup every minute
-- SELECT cron.schedule('cleanup-expired-pending', '* * * * *', 'SELECT cleanup_expired_pending()');
