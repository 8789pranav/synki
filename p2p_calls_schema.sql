-- ============================================================================
-- P2P CALLS SCHEMA
-- Run this in Supabase SQL Editor to enable P2P calling
-- ============================================================================

-- 1. PENDING CALLS TABLE (P2P Incoming Calls)
CREATE TABLE IF NOT EXISTS pending_calls (
    id TEXT PRIMARY KEY,  -- Room name as ID
    caller_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    caller_name TEXT NOT NULL,
    target_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    room_name TEXT NOT NULL,
    status TEXT DEFAULT 'ringing' CHECK (status IN ('ringing', 'answered', 'declined', 'missed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_calls_target ON pending_calls(target_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_calls_created ON pending_calls(created_at DESC);

ALTER TABLE pending_calls ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service can manage calls" ON pending_calls
    FOR ALL USING (auth.role() = 'service_role');

-- Users can view calls involving them
CREATE POLICY "Users can view own calls" ON pending_calls
    FOR SELECT USING (auth.uid() = target_id OR auth.uid() = caller_id);

-- Users can update calls targeting them
CREATE POLICY "Users can update calls for them" ON pending_calls
    FOR UPDATE USING (auth.uid() = target_id);


-- 2. USER SETTINGS TABLE (for auto-reply)
CREATE TABLE IF NOT EXISTS user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    
    -- Auto-reply settings
    auto_reply_enabled BOOLEAN DEFAULT FALSE,
    auto_reply_message TEXT DEFAULT 'Main abhi busy hoon, please message chhod do',
    auto_reply_voice TEXT DEFAULT 'sweet',
    auto_reply_when TEXT DEFAULT 'offline',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service can manage settings" ON user_settings
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users can view own settings" ON user_settings
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own settings" ON user_settings
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own settings" ON user_settings
    FOR INSERT WITH CHECK (auth.uid() = user_id);


-- 3. AUTO REPLY MESSAGES TABLE
CREATE TABLE IF NOT EXISTS auto_reply_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    caller_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
    caller_name TEXT,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE auto_reply_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service can manage messages" ON auto_reply_messages
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users can view own messages" ON auto_reply_messages
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own messages" ON auto_reply_messages
    FOR UPDATE USING (auth.uid() = user_id);


-- 4. USER PRESENCE TABLE (online status)
CREATE TABLE IF NOT EXISTS user_presence (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'offline' CHECK (status IN ('online', 'away', 'busy', 'in_call', 'offline')),
    last_seen TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_presence ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service can manage presence" ON user_presence
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Users can view presence" ON user_presence
    FOR SELECT USING (true);

CREATE POLICY "Users can update own presence" ON user_presence
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own presence" ON user_presence
    FOR INSERT WITH CHECK (auth.uid() = user_id);


-- Done!
-- Now restart your API server and test the P2P calling feature.
