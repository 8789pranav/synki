-- =====================================================
-- SYNKI LAYERED MEMORY ARCHITECTURE
-- PostgreSQL + pgvector schema for intelligent memory
-- =====================================================

-- Enable pgvector extension for semantic recall
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- L3: LONG-TERM PROFILE MEMORY
-- Durable user facts that persist forever
-- =====================================================

-- User preferences and stable facts
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Basic preferences
    preferred_language TEXT DEFAULT 'hinglish',
    timezone TEXT DEFAULT 'Asia/Kolkata',
    persona_mode TEXT DEFAULT 'girlfriend',
    
    -- Communication patterns
    usual_chat_hours JSONB DEFAULT '[]'::jsonb,  -- ["morning", "night"]
    response_style TEXT DEFAULT 'caring',
    
    -- Stable facts (JSONB for flexibility)
    facts JSONB DEFAULT '{}'::jsonb,
    -- Example: {"favorite_movies": ["3 Idiots", "DDLJ"], "skin_type": "oily", "work_hours": "9-6"}
    
    preferences JSONB DEFAULT '{}'::jsonb,
    -- Example: {"likes_black_shirts": true, "prefers_light_cream": true}
    
    emotional_patterns JSONB DEFAULT '{}'::jsonb,
    -- Example: {"tired_at_night": true, "stressed_on_mondays": true}
    
    -- Metadata
    confidence_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- Individual memory facts (granular storage)
CREATE TABLE IF NOT EXISTS memory_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Categorization
    category TEXT NOT NULL,  -- 'preference', 'habit', 'personal', 'medical', 'hobby'
    subcategory TEXT,        -- 'movie', 'food', 'sleep', 'medicine'
    
    -- The actual fact
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    fact_metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Source and confidence
    source TEXT DEFAULT 'conversation',  -- 'conversation', 'explicit', 'inferred'
    confidence FLOAT DEFAULT 0.7,
    mention_count INT DEFAULT 1,
    
    -- Timestamps
    first_mentioned_at TIMESTAMPTZ DEFAULT NOW(),
    last_mentioned_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Prevent duplicates
    UNIQUE(user_id, category, fact_key)
);

-- Index for fast fact lookup
CREATE INDEX IF NOT EXISTS idx_memory_facts_user_category ON memory_facts(user_id, category);
CREATE INDEX IF NOT EXISTS idx_memory_facts_key ON memory_facts(fact_key);

-- =====================================================
-- L2: THREAD MEMORY
-- Conversation threads (movie_discussion, work_stress)
-- =====================================================

CREATE TABLE IF NOT EXISTS conversation_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Thread identification
    thread_type TEXT NOT NULL,  -- 'movie_discussion', 'work_stress', 'skincare', 'general'
    title TEXT NOT NULL,
    
    -- Status
    status TEXT DEFAULT 'active',  -- 'active', 'resolved', 'archived'
    
    -- Content
    summary TEXT,
    summary_jsonb JSONB DEFAULT '{}'::jsonb,
    -- Example: {"main_topic": "3 Idiots movie", "user_sentiment": "curious", "key_points": [...]}
    
    -- Related entities
    entities JSONB DEFAULT '[]'::jsonb,
    -- Example: [{"type": "movie", "value": "3 Idiots", "mentioned_at": "..."}]
    
    -- Pending follow-ups
    pending_followup TEXT,
    followup_context JSONB DEFAULT '{}'::jsonb,
    
    -- Expiration (for auto-cleanup)
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
    
    -- Timestamps
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for thread lookup
CREATE INDEX IF NOT EXISTS idx_threads_user_status ON conversation_threads(user_id, status);
CREATE INDEX IF NOT EXISTS idx_threads_type ON conversation_threads(thread_type);
CREATE INDEX IF NOT EXISTS idx_threads_expires ON conversation_threads(expires_at);

-- Thread entities (normalized)
CREATE TABLE IF NOT EXISTS thread_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Entity details
    entity_type TEXT NOT NULL,  -- 'movie', 'person', 'place', 'product', 'time'
    entity_value TEXT NOT NULL,
    entity_metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Confidence and timing
    confidence FLOAT DEFAULT 0.8,
    mentioned_at TIMESTAMPTZ DEFAULT NOW(),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_thread_entities_thread ON thread_entities(thread_id);
CREATE INDEX IF NOT EXISTS idx_thread_entities_type ON thread_entities(entity_type, entity_value);

-- =====================================================
-- L4: SEMANTIC RECALL MEMORY (pgvector)
-- Embeddings for similarity search
-- =====================================================

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Source reference
    source_type TEXT NOT NULL,  -- 'message', 'thread_summary', 'fact', 'event'
    source_id UUID,
    
    -- Content
    content_text TEXT NOT NULL,
    content_summary TEXT,
    
    -- Vector embedding (1536 dimensions for OpenAI ada-002)
    embedding vector(1536),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_vector ON memory_embeddings 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user ON memory_embeddings(user_id, source_type);

-- =====================================================
-- L6: SUMMARIES AND EVENT MEMORY
-- Daily summaries, session summaries, important events
-- =====================================================

CREATE TABLE IF NOT EXISTS memory_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Summary type
    summary_type TEXT NOT NULL,  -- 'daily', 'session', 'weekly', 'thread'
    
    -- Reference
    reference_date DATE,
    session_id TEXT,
    thread_id UUID REFERENCES conversation_threads(id) ON DELETE SET NULL,
    
    -- Content
    summary_text TEXT NOT NULL,
    key_topics JSONB DEFAULT '[]'::jsonb,
    key_entities JSONB DEFAULT '[]'::jsonb,
    emotional_summary JSONB DEFAULT '{}'::jsonb,
    
    -- Embedding for semantic search
    embedding vector(1536),
    
    -- Timestamps
    period_start TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_summaries_user_type ON memory_summaries(user_id, summary_type);
CREATE INDEX IF NOT EXISTS idx_summaries_date ON memory_summaries(reference_date);

-- Important events (birthdays, milestones, significant moments)
CREATE TABLE IF NOT EXISTS important_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Event details
    event_type TEXT NOT NULL,  -- 'birthday', 'anniversary', 'milestone', 'memory'
    event_title TEXT NOT NULL,
    event_description TEXT,
    
    -- Date (can be recurring)
    event_date DATE,
    is_recurring BOOLEAN DEFAULT FALSE,
    recurrence_pattern TEXT,  -- 'yearly', 'monthly'
    
    -- Reminder settings
    remind_before_days INT DEFAULT 1,
    last_reminded_at TIMESTAMPTZ,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_user_date ON important_events(user_id, event_date);
CREATE INDEX IF NOT EXISTS idx_events_type ON important_events(event_type);

-- =====================================================
-- L5: ANTI-REPETITION MEMORY
-- Track recent patterns to avoid repetition
-- =====================================================

CREATE TABLE IF NOT EXISTS anti_repetition_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id TEXT,
    
    -- Pattern tracking
    pattern_type TEXT NOT NULL,  -- 'opener', 'sentence', 'topic', 'suggestion', 'question'
    pattern_value TEXT NOT NULL,
    pattern_hash TEXT,  -- For fast lookup
    
    -- Timestamps
    used_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Auto-expire old entries
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '3 days')
);

CREATE INDEX IF NOT EXISTS idx_anti_rep_user_type ON anti_repetition_log(user_id, pattern_type);
CREATE INDEX IF NOT EXISTS idx_anti_rep_hash ON anti_repetition_log(pattern_hash);
CREATE INDEX IF NOT EXISTS idx_anti_rep_expires ON anti_repetition_log(expires_at);

-- =====================================================
-- VIEWS FOR EASY QUERYING
-- =====================================================

-- Active threads for a user
CREATE OR REPLACE VIEW active_threads AS
SELECT * FROM conversation_threads
WHERE status = 'active' AND expires_at > NOW()
ORDER BY last_message_at DESC;

-- Recent memory facts
CREATE OR REPLACE VIEW recent_facts AS
SELECT * FROM memory_facts
WHERE last_mentioned_at > NOW() - INTERVAL '7 days'
ORDER BY last_mentioned_at DESC;

-- =====================================================
-- FUNCTIONS
-- =====================================================

-- Function to find similar memories using vector search
CREATE OR REPLACE FUNCTION find_similar_memories(
    p_user_id UUID,
    p_embedding vector(1536),
    p_limit INT DEFAULT 5,
    p_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id UUID,
    source_type TEXT,
    content_text TEXT,
    content_summary TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        me.id,
        me.source_type,
        me.content_text,
        me.content_summary,
        1 - (me.embedding <=> p_embedding) AS similarity
    FROM memory_embeddings me
    WHERE me.user_id = p_user_id
      AND 1 - (me.embedding <=> p_embedding) > p_threshold
    ORDER BY me.embedding <=> p_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function to resolve entity reference (e.g., "that movie")
CREATE OR REPLACE FUNCTION resolve_entity_reference(
    p_user_id UUID,
    p_entity_type TEXT,
    p_hours_back INT DEFAULT 24
)
RETURNS TABLE (
    entity_value TEXT,
    thread_id UUID,
    thread_title TEXT,
    mentioned_at TIMESTAMPTZ,
    confidence FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        te.entity_value,
        te.thread_id,
        ct.title AS thread_title,
        te.mentioned_at,
        te.confidence
    FROM thread_entities te
    JOIN conversation_threads ct ON te.thread_id = ct.id
    WHERE te.user_id = p_user_id
      AND te.entity_type = p_entity_type
      AND te.mentioned_at > NOW() - (p_hours_back || ' hours')::INTERVAL
    ORDER BY te.mentioned_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to check if pattern was recently used
CREATE OR REPLACE FUNCTION is_pattern_recent(
    p_user_id UUID,
    p_pattern_type TEXT,
    p_pattern_hash TEXT,
    p_hours_back INT DEFAULT 24
)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM anti_repetition_log
        WHERE user_id = p_user_id
          AND pattern_type = p_pattern_type
          AND pattern_hash = p_pattern_hash
          AND used_at > NOW() - (p_hours_back || ' hours')::INTERVAL
    );
END;
$$ LANGUAGE plpgsql;

-- Cleanup function for expired data
CREATE OR REPLACE FUNCTION cleanup_expired_memory()
RETURNS void AS $$
BEGIN
    -- Archive expired threads
    UPDATE conversation_threads 
    SET status = 'archived'
    WHERE expires_at < NOW() AND status = 'active';
    
    -- Delete old anti-repetition logs
    DELETE FROM anti_repetition_log
    WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- ROW LEVEL SECURITY
-- =====================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE thread_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE important_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE anti_repetition_log ENABLE ROW LEVEL SECURITY;

-- Policies (users can only access their own data)
CREATE POLICY "Users can access own profiles" ON user_profiles
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own facts" ON memory_facts
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own threads" ON conversation_threads
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own entities" ON thread_entities
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own embeddings" ON memory_embeddings
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own summaries" ON memory_summaries
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own events" ON important_events
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own anti-rep log" ON anti_repetition_log
    FOR ALL USING (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access profiles" ON user_profiles
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access facts" ON memory_facts
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access threads" ON conversation_threads
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access entities" ON thread_entities
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access embeddings" ON memory_embeddings
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access summaries" ON memory_summaries
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access events" ON important_events
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');

CREATE POLICY "Service role full access anti-rep" ON anti_repetition_log
    FOR ALL USING (auth.jwt()->>'role' = 'service_role');
