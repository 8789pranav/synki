-- ============================================================================
-- SYNKI DATABASE SCHEMA
-- Run this in your Supabase SQL Editor
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- PROFILES TABLE
-- Stores user profile information
-- ============================================================================
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Baby',
    email TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Policies for profiles
CREATE POLICY "Users can view own profile" ON profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile" ON profiles
    FOR INSERT WITH CHECK (auth.uid() = id);

-- Allow viewing connected users' profiles
CREATE POLICY "Users can view connected profiles" ON profiles
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM synki_connections 
            WHERE status = 'accepted' 
            AND ((user_id = auth.uid() AND connected_user_id = profiles.id)
                 OR (connected_user_id = auth.uid() AND user_id = profiles.id))
        )
    );

-- ============================================================================
-- SYNKI CONNECTIONS TABLE (Social Friend System)
-- Two-way connections between Synki users
-- ============================================================================
CREATE TABLE IF NOT EXISTS synki_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,         -- Who sent request
    connected_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL, -- Who receives
    relationship TEXT DEFAULT 'family',  -- 'family', 'friend', 'caregiver', 'parent', 'child'
    nickname TEXT,                       -- Custom name for this connection
    status TEXT DEFAULT 'pending',       -- 'pending', 'accepted', 'rejected', 'blocked'
    permissions JSONB DEFAULT '{"can_schedule_calls": true, "can_see_status": true, "can_send_messages": true}',
    notes TEXT,                          -- Private notes about the connection
    created_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, connected_user_id),  -- Only one connection between two users
    CHECK (user_id != connected_user_id) -- Can't connect to yourself
);

CREATE INDEX IF NOT EXISTS idx_connections_user ON synki_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_connections_connected ON synki_connections(connected_user_id);
CREATE INDEX IF NOT EXISTS idx_connections_status ON synki_connections(status);

ALTER TABLE synki_connections ENABLE ROW LEVEL SECURITY;

-- Users can see connections where they are involved
CREATE POLICY "Users can view own connections" ON synki_connections
    FOR SELECT USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

-- Users can send connection requests
CREATE POLICY "Users can send connection requests" ON synki_connections
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can update connections they're part of
CREATE POLICY "Users can update own connections" ON synki_connections
    FOR UPDATE USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

-- Users can delete their own sent requests or accepted connections
CREATE POLICY "Users can delete own connections" ON synki_connections
    FOR DELETE USING (auth.uid() = user_id OR auth.uid() = connected_user_id);

-- ============================================================================
-- SYNKI CODES TABLE (Easy sharing codes like Discord)
-- 6-character unique codes for easy connection
-- ============================================================================
CREATE TABLE IF NOT EXISTS synki_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    code TEXT NOT NULL UNIQUE,           -- e.g., "SH1V4M", "M0M123"
    custom_code TEXT UNIQUE,             -- User can set custom code (premium feature)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_synki_codes_code ON synki_codes(code);
CREATE INDEX IF NOT EXISTS idx_synki_codes_custom ON synki_codes(custom_code) WHERE custom_code IS NOT NULL;

ALTER TABLE synki_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view codes" ON synki_codes FOR SELECT USING (true);
CREATE POLICY "Users can update own code" ON synki_codes FOR UPDATE USING (auth.uid() = user_id);

-- ============================================================================
-- FUNCTION: Generate unique Synki code
-- ============================================================================
CREATE OR REPLACE FUNCTION generate_synki_code()
RETURNS TEXT AS $$
DECLARE
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';  -- No I, O, 0, 1 for clarity
    result TEXT := '';
    i INTEGER;
BEGIN
    FOR i IN 1..6 LOOP
        result := result || substr(chars, floor(random() * length(chars) + 1)::int, 1);
    END LOOP;
    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- FUNCTION: Auto-create Synki code on user signup
-- ============================================================================
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

-- Trigger to create code when profile is created
DROP TRIGGER IF EXISTS create_synki_code_trigger ON profiles;
CREATE TRIGGER create_synki_code_trigger
    AFTER INSERT ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION create_synki_code_for_user();

-- ============================================================================
-- FUNCTION: Find user by Synki code
-- ============================================================================
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

-- ============================================================================
-- FUNCTION: Get all connections for a user
-- ============================================================================
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

-- ============================================================================
-- FUNCTION: Send connection request
-- ============================================================================
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
    RETURNING id INTO v_connection_id;
    
    RETURN QUERY SELECT true, 'Connection request sent'::TEXT, v_connection_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- FUNCTION: Accept/Reject connection request
-- ============================================================================
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
            nickname = COALESCE(p_nickname, nickname)
        WHERE id = p_connection_id;
        
        RETURN QUERY SELECT true, 'Connection accepted!'::TEXT;
    ELSE
        UPDATE synki_connections
        SET status = 'rejected'
        WHERE id = p_connection_id;
        
        RETURN QUERY SELECT true, 'Connection declined'::TEXT;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- MEMORIES TABLE
-- Stores long-term memory about users (preferences, facts, patterns)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    name TEXT,
    preferences JSONB DEFAULT '{}',
    facts JSONB DEFAULT '[]',
    sleep_pattern TEXT,
    common_topics TEXT[],
    last_mood TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- Enable RLS
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Policies for memories
CREATE POLICY "Users can view own memories" ON memories
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own memories" ON memories
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own memories" ON memories
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Service role can manage all memories" ON memories
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- CHAT HISTORY TABLE
-- Stores conversation history
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    emotion TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at DESC);

-- Enable RLS
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

-- Policies for chat_history
CREATE POLICY "Users can view own chat history" ON chat_history
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chat" ON chat_history
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Service role can manage all chats" ON chat_history
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- SESSIONS TABLE
-- Stores voice session information
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    room_name TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    turn_count INTEGER DEFAULT 0,
    detected_emotions TEXT[],
    topics_discussed TEXT[],
    metadata JSONB DEFAULT '{}'
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

-- Enable RLS
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

-- Policies for sessions
CREATE POLICY "Users can view own sessions" ON sessions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage all sessions" ON sessions
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- FUNCTION: Get user conversation summary
-- ============================================================================
CREATE OR REPLACE FUNCTION get_conversation_summary(p_user_id UUID)
RETURNS TABLE (
    total_messages BIGINT,
    total_sessions BIGINT,
    most_common_emotion TEXT,
    last_active TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*) FROM chat_history WHERE user_id = p_user_id) as total_messages,
        (SELECT COUNT(*) FROM sessions WHERE user_id = p_user_id) as total_sessions,
        (SELECT emotion FROM chat_history WHERE user_id = p_user_id AND emotion IS NOT NULL 
         GROUP BY emotion ORDER BY COUNT(*) DESC LIMIT 1) as most_common_emotion,
        (SELECT MAX(created_at) FROM chat_history WHERE user_id = p_user_id) as last_active;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- FUNCTION: Get recent context for LLM
-- ============================================================================
CREATE OR REPLACE FUNCTION get_recent_context(p_user_id UUID, p_limit INTEGER DEFAULT 10)
RETURNS TABLE (
    role TEXT,
    content TEXT,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT ch.role, ch.content, ch.created_at
    FROM chat_history ch
    WHERE ch.user_id = p_user_id
    ORDER BY ch.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- USER PROFILES - SHORT TERM
-- Rolling 5-6 day behavioral snapshot
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_profiles_short_term (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    profile_data JSONB DEFAULT '{}',
    -- Quick access fields for queries
    dominant_mood TEXT,
    mood_trend TEXT,
    stress_level TEXT,
    activity_level TEXT,
    data_points INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_short_term_user_id ON user_profiles_short_term(user_id);
CREATE INDEX IF NOT EXISTS idx_short_term_updated ON user_profiles_short_term(updated_at DESC);

-- Enable RLS
ALTER TABLE user_profiles_short_term ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Users can view own short-term profile" ON user_profiles_short_term
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own short-term profile" ON user_profiles_short_term
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own short-term profile" ON user_profiles_short_term
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Service role can manage all short-term profiles" ON user_profiles_short_term
    FOR ALL USING (auth.role() = 'service_role');

-- Trigger for updated_at
CREATE TRIGGER update_short_term_profile_updated_at
    BEFORE UPDATE ON user_profiles_short_term
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- USER PROFILES - LONG TERM
-- Permanent psychological profile
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_profiles_long_term (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    profile_data JSONB DEFAULT '{}',
    -- Quick access fields
    personality_summary TEXT,
    emotional_baseline TEXT,
    confidence_score FLOAT DEFAULT 0,
    conversations_analyzed INTEGER DEFAULT 0,
    -- Important flags for quick reference
    is_morning_person BOOLEAN,
    dominant_traits TEXT[],
    core_values TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_long_term_user_id ON user_profiles_long_term(user_id);
CREATE INDEX IF NOT EXISTS idx_long_term_confidence ON user_profiles_long_term(confidence_score DESC);

-- Enable RLS
ALTER TABLE user_profiles_long_term ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Users can view own long-term profile" ON user_profiles_long_term
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own long-term profile" ON user_profiles_long_term
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own long-term profile" ON user_profiles_long_term
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Service role can manage all long-term profiles" ON user_profiles_long_term
    FOR ALL USING (auth.role() = 'service_role');

-- Trigger for updated_at
CREATE TRIGGER update_long_term_profile_updated_at
    BEFORE UPDATE ON user_profiles_long_term
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- CONVERSATION SUMMARIES
-- For weekly analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    topics TEXT[],
    emotions_detected TEXT[],
    key_insights JSONB DEFAULT '{}',
    analyzed_for_profile BOOLEAN DEFAULT FALSE,
    conversation_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for weekly analysis queries
CREATE INDEX IF NOT EXISTS idx_summaries_user_date ON conversation_summaries(user_id, conversation_date DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_not_analyzed ON conversation_summaries(user_id, analyzed_for_profile) 
    WHERE analyzed_for_profile = FALSE;

-- Enable RLS
ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY "Users can view own summaries" ON conversation_summaries
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage all summaries" ON conversation_summaries
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- FUNCTION: Get weekly summaries for analysis
-- ============================================================================
CREATE OR REPLACE FUNCTION get_weekly_summaries_for_analysis(p_user_id UUID)
RETURNS TABLE (
    id UUID,
    summary TEXT,
    topics TEXT[],
    emotions_detected TEXT[],
    conversation_date DATE
) AS $$
BEGIN
    RETURN QUERY
    SELECT cs.id, cs.summary, cs.topics, cs.emotions_detected, cs.conversation_date
    FROM conversation_summaries cs
    WHERE cs.user_id = p_user_id
      AND cs.analyzed_for_profile = FALSE
      AND cs.conversation_date >= CURRENT_DATE - INTERVAL '7 days'
    ORDER BY cs.conversation_date ASC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- FUNCTION: Mark summaries as analyzed
-- ============================================================================
CREATE OR REPLACE FUNCTION mark_summaries_analyzed(p_summary_ids UUID[])
RETURNS VOID AS $$
BEGIN
    UPDATE conversation_summaries
    SET analyzed_for_profile = TRUE
    WHERE id = ANY(p_summary_ids);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- SCHEDULED CALLS TABLE
-- Server-side call scheduling for proactive contacts
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduled_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'triggered', 'answered', 'missed', 'cancelled')),
    call_type TEXT DEFAULT 'scheduled' CHECK (call_type IN ('scheduled', 'proactive', 'reminder')),
    message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    triggered_at TIMESTAMPTZ,
    answered_at TIMESTAMPTZ
);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_user_id ON scheduled_calls(user_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_status ON scheduled_calls(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_scheduled_at ON scheduled_calls(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_pending ON scheduled_calls(scheduled_at) WHERE status = 'pending';

-- Enable RLS
ALTER TABLE scheduled_calls ENABLE ROW LEVEL SECURITY;

-- Policies for scheduled_calls
CREATE POLICY "Users can view own scheduled calls" ON scheduled_calls
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own scheduled calls" ON scheduled_calls
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own scheduled calls" ON scheduled_calls
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own scheduled calls" ON scheduled_calls
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage all scheduled calls" ON scheduled_calls
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- FUNCTION: Get pending scheduled calls (for scheduler)
-- ============================================================================
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

-- ============================================================================
-- PUSH TOKENS TABLE (FCM)
-- Stores Firebase Cloud Messaging tokens for push notifications
-- ============================================================================
CREATE TABLE IF NOT EXISTS push_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    token TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'web',  -- 'web', 'android', 'ios'
    device_name TEXT,
    browser TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, token)
);

-- Indexes for push_tokens
CREATE INDEX IF NOT EXISTS idx_push_tokens_user_id ON push_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_push_tokens_active ON push_tokens(user_id) WHERE is_active = true;

-- Enable RLS
ALTER TABLE push_tokens ENABLE ROW LEVEL SECURITY;

-- Policies for push_tokens
CREATE POLICY "Users can view own push tokens" ON push_tokens
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own push tokens" ON push_tokens
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own push tokens" ON push_tokens
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own push tokens" ON push_tokens
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Service role can manage all push tokens" ON push_tokens
    USING (auth.role() = 'service_role');

-- Function to get active tokens for a user
CREATE OR REPLACE FUNCTION get_user_push_tokens(p_user_id UUID)
RETURNS TABLE(token TEXT, platform TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT pt.token, pt.platform
    FROM push_tokens pt
    WHERE pt.user_id = p_user_id
      AND pt.is_active = true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- LINKED USERS TABLE (Family/Care Recipients)
-- Stores family members or care recipients that can receive calls
-- ============================================================================
CREATE TABLE IF NOT EXISTS linked_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    name TEXT NOT NULL,
    relationship TEXT NOT NULL,  -- 'mom', 'dad', 'grandma', 'friend', etc.
    phone TEXT,
    email TEXT,
    push_token TEXT,  -- FCM token if they have the app
    avatar_emoji TEXT DEFAULT '👵',
    language_preference TEXT DEFAULT 'hinglish',
    speaking_pace TEXT DEFAULT 'slow',  -- 'normal', 'slow', 'very_slow'
    notes TEXT,  -- Any special notes about the person
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_linked_users_owner ON linked_users(owner_id);

ALTER TABLE linked_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own linked users" ON linked_users
    FOR SELECT USING (auth.uid() = owner_id);

CREATE POLICY "Users can insert own linked users" ON linked_users
    FOR INSERT WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update own linked users" ON linked_users
    FOR UPDATE USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete own linked users" ON linked_users
    FOR DELETE USING (auth.uid() = owner_id);

-- ============================================================================
-- CALL TOPICS TABLE (Conversation Topics/Scripts)
-- Predefined topics for scheduled calls
-- ============================================================================
CREATE TABLE IF NOT EXISTS call_topics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    emoji TEXT DEFAULT '💬',
    prompts JSONB DEFAULT '[]',  -- Array of questions/prompts for agent
    persona_adjustments JSONB DEFAULT '{}',  -- tone, pace, language adjustments
    duration_minutes INT DEFAULT 5,
    is_preset BOOLEAN DEFAULT false,  -- System preset vs user created
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_topics_owner ON call_topics(owner_id);

ALTER TABLE call_topics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own call topics" ON call_topics
    FOR SELECT USING (auth.uid() = owner_id OR is_preset = true);

CREATE POLICY "Users can insert own call topics" ON call_topics
    FOR INSERT WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update own call topics" ON call_topics
    FOR UPDATE USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete own call topics" ON call_topics
    FOR DELETE USING (auth.uid() = owner_id AND is_preset = false);

-- ============================================================================
-- DELEGATED CALLS TABLE (Calls to linked users)
-- Scheduled calls that go to family members
-- ============================================================================
CREATE TABLE IF NOT EXISTS delegated_calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    linked_user_id UUID REFERENCES linked_users(id) ON DELETE CASCADE NOT NULL,
    topic_id UUID REFERENCES call_topics(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending',  -- 'pending', 'triggered', 'completed', 'missed', 'cancelled'
    custom_message TEXT,
    call_duration_seconds INT,
    call_summary TEXT,  -- AI generated summary of the call
    triggered_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_delegated_calls_owner ON delegated_calls(owner_id);
CREATE INDEX IF NOT EXISTS idx_delegated_calls_linked ON delegated_calls(linked_user_id);
CREATE INDEX IF NOT EXISTS idx_delegated_calls_status ON delegated_calls(status, scheduled_at);

ALTER TABLE delegated_calls ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own delegated calls" ON delegated_calls
    FOR SELECT USING (auth.uid() = owner_id);

CREATE POLICY "Users can insert own delegated calls" ON delegated_calls
    FOR INSERT WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Users can update own delegated calls" ON delegated_calls
    FOR UPDATE USING (auth.uid() = owner_id);

CREATE POLICY "Users can delete own delegated calls" ON delegated_calls
    FOR DELETE USING (auth.uid() = owner_id);

CREATE POLICY "Service role can manage all delegated calls" ON delegated_calls
    FOR ALL USING (auth.role() = 'service_role');

-- Function to get pending delegated calls
CREATE OR REPLACE FUNCTION get_pending_delegated_calls()
RETURNS TABLE (
    id UUID,
    owner_id UUID,
    linked_user_id UUID,
    linked_user_name TEXT,
    linked_user_phone TEXT,
    linked_user_push_token TEXT,
    topic_id UUID,
    topic_title TEXT,
    topic_prompts JSONB,
    scheduled_at TIMESTAMPTZ,
    custom_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dc.id, 
        dc.owner_id, 
        dc.linked_user_id,
        lu.name as linked_user_name,
        lu.phone as linked_user_phone,
        lu.push_token as linked_user_push_token,
        dc.topic_id,
        ct.title as topic_title,
        ct.prompts as topic_prompts,
        dc.scheduled_at, 
        dc.custom_message
    FROM delegated_calls dc
    JOIN linked_users lu ON dc.linked_user_id = lu.id
    LEFT JOIN call_topics ct ON dc.topic_id = ct.id
    WHERE dc.status = 'pending'
      AND dc.scheduled_at <= NOW()
    ORDER BY dc.scheduled_at ASC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- USER PRESENCE TABLE (Online Status Tracking)
-- Tracks real-time online status of users
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_presence (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'offline' CHECK (status IN ('online', 'away', 'busy', 'in_call', 'offline')),
    activity TEXT,  -- e.g., 'talking_to_synki', 'browsing', 'scheduling'
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_presence_status ON user_presence(status);
CREATE INDEX IF NOT EXISTS idx_presence_last_seen ON user_presence(last_seen DESC);

-- Enable RLS
ALTER TABLE user_presence ENABLE ROW LEVEL SECURITY;

-- Users can view their own presence
CREATE POLICY "Users can view own presence" ON user_presence
    FOR SELECT USING (auth.uid() = user_id);

-- Users can update their own presence
CREATE POLICY "Users can update own presence" ON user_presence
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can insert their own presence
CREATE POLICY "Users can insert own presence" ON user_presence
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can view presence of connected users
CREATE POLICY "Users can view connected users presence" ON user_presence
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM synki_connections 
            WHERE status = 'accepted' 
            AND ((user_id = auth.uid() AND connected_user_id = user_presence.user_id)
                 OR (connected_user_id = auth.uid() AND user_id = user_presence.user_id))
        )
    );

-- Service role can do everything
CREATE POLICY "Service role full access presence" ON user_presence
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;
