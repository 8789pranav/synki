-- ============================================================================
-- SYNKI CONNECTIONS MIGRATION
-- Complete SQL for Social Connections Feature
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Enable UUID extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- DROP EXISTING (for clean re-run - comment out in production)
-- ============================================================================
-- DROP TABLE IF EXISTS user_presence CASCADE;
-- DROP TABLE IF EXISTS synki_codes CASCADE;
-- DROP TABLE IF EXISTS synki_connections CASCADE;
-- DROP FUNCTION IF EXISTS generate_synki_code();
-- DROP FUNCTION IF EXISTS create_synki_code_for_user();
-- DROP FUNCTION IF EXISTS find_user_by_code(TEXT);
-- DROP FUNCTION IF EXISTS get_user_connections(UUID, TEXT);
-- DROP FUNCTION IF EXISTS send_connection_request(UUID, TEXT, TEXT, TEXT);
-- DROP FUNCTION IF EXISTS respond_to_connection(UUID, UUID, BOOLEAN, TEXT);

-- ============================================================================
-- 1. SYNKI CONNECTIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS synki_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    connected_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    relationship TEXT DEFAULT 'family',
    nickname TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'blocked')),
    permissions JSONB DEFAULT '{"can_schedule_calls": true, "can_see_status": true, "can_send_messages": true}',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, connected_user_id),
    CHECK (user_id != connected_user_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_connections_user ON synki_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_connections_connected ON synki_connections(connected_user_id);
CREATE INDEX IF NOT EXISTS idx_connections_status ON synki_connections(status);

-- RLS
ALTER TABLE synki_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own connections" ON synki_connections;
CREATE POLICY "Users can view own connections" ON synki_connections
    FOR SELECT USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

DROP POLICY IF EXISTS "Users can send connection requests" ON synki_connections;
CREATE POLICY "Users can send connection requests" ON synki_connections
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own connections" ON synki_connections;
CREATE POLICY "Users can update own connections" ON synki_connections
    FOR UPDATE USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

DROP POLICY IF EXISTS "Users can delete own connections" ON synki_connections;
CREATE POLICY "Users can delete own connections" ON synki_connections
    FOR DELETE USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

DROP POLICY IF EXISTS "Service role full access connections" ON synki_connections;
CREATE POLICY "Service role full access connections" ON synki_connections
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- 2. SYNKI CODES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS synki_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,
    custom_code TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_synki_codes_code ON synki_codes(code);
CREATE INDEX IF NOT EXISTS idx_synki_codes_custom ON synki_codes(custom_code) WHERE custom_code IS NOT NULL;

-- RLS
ALTER TABLE synki_codes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can view codes" ON synki_codes;
CREATE POLICY "Anyone can view codes" ON synki_codes FOR SELECT USING (true);

DROP POLICY IF EXISTS "Users can update own code" ON synki_codes;
CREATE POLICY "Users can update own code" ON synki_codes FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Service role full access codes" ON synki_codes;
CREATE POLICY "Service role full access codes" ON synki_codes
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- 3. USER PRESENCE TABLE (Online Status)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_presence (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'offline' CHECK (status IN ('online', 'away', 'busy', 'in_call', 'offline')),
    activity TEXT,
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_presence_status ON user_presence(status);
CREATE INDEX IF NOT EXISTS idx_presence_last_seen ON user_presence(last_seen DESC);

-- RLS
ALTER TABLE user_presence ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own presence" ON user_presence;
CREATE POLICY "Users can view own presence" ON user_presence
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own presence" ON user_presence;
CREATE POLICY "Users can update own presence" ON user_presence
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own presence" ON user_presence;
CREATE POLICY "Users can insert own presence" ON user_presence
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view connected presence" ON user_presence;
CREATE POLICY "Users can view connected presence" ON user_presence
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM synki_connections 
            WHERE status = 'accepted' 
            AND ((user_id = auth.uid() AND connected_user_id = user_presence.user_id)
                 OR (connected_user_id = auth.uid() AND user_id = user_presence.user_id))
        )
    );

DROP POLICY IF EXISTS "Service role full access presence" ON user_presence;
CREATE POLICY "Service role full access presence" ON user_presence
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- 4. FUNCTIONS
-- ============================================================================

-- Generate random 6-char code
CREATE OR REPLACE FUNCTION generate_synki_code()
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    result TEXT := '';
    i INTEGER;
BEGIN
    FOR i IN 1..6 LOOP
        result := result || substr(chars, floor(random() * length(chars) + 1)::int, 1);
    END LOOP;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Auto-create code on profile creation
CREATE OR REPLACE FUNCTION create_synki_code_for_user()
RETURNS TRIGGER AS $$
DECLARE
    new_code TEXT;
    attempts INT := 0;
BEGIN
    LOOP
        new_code := generate_synki_code();
        BEGIN
            INSERT INTO synki_codes (user_id, code) VALUES (NEW.id, new_code);
            EXIT;
        EXCEPTION WHEN unique_violation THEN
            attempts := attempts + 1;
            IF attempts > 10 THEN
                RAISE EXCEPTION 'Could not generate unique code';
            END IF;
        END;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger for auto-creating code
DROP TRIGGER IF EXISTS create_synki_code_trigger ON profiles;
CREATE TRIGGER create_synki_code_trigger
    AFTER INSERT ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION create_synki_code_for_user();

-- Find user by code
CREATE OR REPLACE FUNCTION find_user_by_code(search_code TEXT)
RETURNS TABLE (
    user_id UUID,
    name TEXT,
    avatar_url TEXT,
    code TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.name, p.avatar_url, sc.code
    FROM profiles p
    JOIN synki_codes sc ON p.id = sc.user_id
    WHERE UPPER(sc.code) = UPPER(search_code) 
       OR UPPER(sc.custom_code) = UPPER(search_code);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get all connections for a user
CREATE OR REPLACE FUNCTION get_user_connections(p_user_id UUID, p_status TEXT DEFAULT NULL)
RETURNS TABLE (
    connection_id UUID,
    other_user_id UUID,
    other_user_name TEXT,
    other_user_avatar TEXT,
    other_user_code TEXT,
    relationship TEXT,
    nickname TEXT,
    status TEXT,
    permissions JSONB,
    is_requester BOOLEAN,
    created_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id as connection_id,
        CASE WHEN c.user_id = p_user_id THEN c.connected_user_id ELSE c.user_id END as other_user_id,
        p.name as other_user_name,
        p.avatar_url as other_user_avatar,
        sc.code as other_user_code,
        c.relationship,
        c.nickname,
        c.status,
        c.permissions,
        (c.user_id = p_user_id) as is_requester,
        c.created_at,
        c.accepted_at
    FROM synki_connections c
    JOIN profiles p ON p.id = CASE WHEN c.user_id = p_user_id THEN c.connected_user_id ELSE c.user_id END
    LEFT JOIN synki_codes sc ON sc.user_id = p.id
    WHERE (c.user_id = p_user_id OR c.connected_user_id = p_user_id)
      AND (p_status IS NULL OR c.status = p_status);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Send connection request
CREATE OR REPLACE FUNCTION send_connection_request(
    p_from_user_id UUID,
    p_to_user_code TEXT,
    p_relationship TEXT DEFAULT 'family',
    p_nickname TEXT DEFAULT NULL
)
RETURNS TABLE (success BOOLEAN, message TEXT, connection_id UUID) AS $$
DECLARE
    v_to_user_id UUID;
    v_connection_id UUID;
    v_existing_status TEXT;
BEGIN
    -- Find user by code
    SELECT user_id INTO v_to_user_id
    FROM synki_codes
    WHERE UPPER(code) = UPPER(p_to_user_code) 
       OR UPPER(custom_code) = UPPER(p_to_user_code);
    
    IF v_to_user_id IS NULL THEN
        RETURN QUERY SELECT false, 'User not found with this code'::TEXT, NULL::UUID;
        RETURN;
    END IF;
    
    IF v_to_user_id = p_from_user_id THEN
        RETURN QUERY SELECT false, 'Cannot connect to yourself'::TEXT, NULL::UUID;
        RETURN;
    END IF;
    
    -- Check existing connection
    SELECT id, status INTO v_connection_id, v_existing_status
    FROM synki_connections
    WHERE (user_id = p_from_user_id AND connected_user_id = v_to_user_id)
       OR (user_id = v_to_user_id AND connected_user_id = p_from_user_id);
    
    IF v_existing_status = 'accepted' THEN
        RETURN QUERY SELECT false, 'Already connected'::TEXT, v_connection_id;
        RETURN;
    ELSIF v_existing_status = 'pending' THEN
        RETURN QUERY SELECT false, 'Request already pending'::TEXT, v_connection_id;
        RETURN;
    ELSIF v_existing_status = 'blocked' THEN
        RETURN QUERY SELECT false, 'Cannot connect to this user'::TEXT, NULL::UUID;
        RETURN;
    END IF;
    
    -- Create new connection request
    INSERT INTO synki_connections (user_id, connected_user_id, relationship, nickname, status)
    VALUES (p_from_user_id, v_to_user_id, p_relationship, p_nickname, 'pending')
    ON CONFLICT (user_id, connected_user_id) DO UPDATE 
    SET status = 'pending', relationship = p_relationship, nickname = p_nickname, updated_at = NOW()
    RETURNING id INTO v_connection_id;
    
    RETURN QUERY SELECT true, 'Connection request sent'::TEXT, v_connection_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Respond to connection request
CREATE OR REPLACE FUNCTION respond_to_connection(
    p_connection_id UUID,
    p_user_id UUID,
    p_accept BOOLEAN,
    p_nickname TEXT DEFAULT NULL
)
RETURNS TABLE (success BOOLEAN, message TEXT) AS $$
DECLARE
    v_connection RECORD;
BEGIN
    -- Get connection
    SELECT * INTO v_connection
    FROM synki_connections
    WHERE id = p_connection_id AND connected_user_id = p_user_id AND status = 'pending';
    
    IF v_connection IS NULL THEN
        RETURN QUERY SELECT false, 'Connection request not found'::TEXT;
        RETURN;
    END IF;
    
    IF p_accept THEN
        UPDATE synki_connections
        SET status = 'accepted',
            accepted_at = NOW(),
            nickname = COALESCE(p_nickname, nickname),
            updated_at = NOW()
        WHERE id = p_connection_id;
        
        RETURN QUERY SELECT true, 'Connection accepted!'::TEXT;
    ELSE
        UPDATE synki_connections
        SET status = 'rejected', updated_at = NOW()
        WHERE id = p_connection_id;
        
        RETURN QUERY SELECT true, 'Connection declined'::TEXT;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- 5. GRANT PERMISSIONS
-- ============================================================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON synki_connections TO anon, authenticated;
GRANT ALL ON synki_codes TO anon, authenticated;
GRANT ALL ON user_presence TO anon, authenticated;
GRANT EXECUTE ON FUNCTION generate_synki_code() TO anon, authenticated;
GRANT EXECUTE ON FUNCTION create_synki_code_for_user() TO anon, authenticated;
GRANT EXECUTE ON FUNCTION find_user_by_code(TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_user_connections(UUID, TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION send_connection_request(UUID, TEXT, TEXT, TEXT) TO anon, authenticated;
GRANT EXECUTE ON FUNCTION respond_to_connection(UUID, UUID, BOOLEAN, TEXT) TO anon, authenticated;

-- ============================================================================
-- 6. CREATE CODES FOR EXISTING USERS (One-time migration)
-- ============================================================================
INSERT INTO synki_codes (user_id, code)
SELECT id, generate_synki_code()
FROM profiles
WHERE id NOT IN (SELECT user_id FROM synki_codes)
ON CONFLICT (user_id) DO NOTHING;

-- ============================================================================
-- DONE! Run this SQL in Supabase SQL Editor
-- ============================================================================
SELECT 'Migration complete! Tables created: synki_connections, synki_codes, user_presence' as status;
