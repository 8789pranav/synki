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
-- GRANT PERMISSIONS
-- ============================================================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;
