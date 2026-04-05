-- Smart Memory System Tables
-- Run this in Supabase SQL Editor

-- Daily Summaries (24-hour detailed summary)
CREATE TABLE IF NOT EXISTS daily_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Mood tracking
    dominant_mood TEXT DEFAULT 'neutral',
    mood_changes JSONB DEFAULT '[]',
    
    -- Topics and activities
    topics_discussed JSONB DEFAULT '[]',
    questions_asked JSONB DEFAULT '[]',
    activities JSONB DEFAULT '[]',
    
    -- Events and notes
    highlights JSONB DEFAULT '[]',
    concerns JSONB DEFAULT '[]',
    positives JSONB DEFAULT '[]',
    
    -- Conversation flow
    last_topic TEXT,
    conversation_ended_on TEXT,
    
    -- Stats
    total_messages INTEGER DEFAULT 0,
    user_messages INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint
    UNIQUE(user_id, date)
);

-- Weekly Summaries (7-day high-level summary)
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    
    -- Mood
    overall_mood TEXT DEFAULT 'neutral',
    mood_trend TEXT DEFAULT 'stable',
    
    -- Topics and events
    recurring_topics JSONB DEFAULT '[]',
    key_events JSONB DEFAULT '[]',
    patterns JSONB DEFAULT '[]',
    
    -- Stats
    total_conversations INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    
    -- Carry forward
    carry_forward JSONB DEFAULT '[]',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Unique constraint
    UNIQUE(user_id, week_start)
);

-- Indexes for fast lookup
CREATE INDEX IF NOT EXISTS idx_daily_summaries_user_date ON daily_summaries(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_weekly_summaries_user_week ON weekly_summaries(user_id, week_start DESC);

-- RLS Policies
ALTER TABLE daily_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_summaries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own daily summaries"
    ON daily_summaries FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own daily summaries"
    ON daily_summaries FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own daily summaries"
    ON daily_summaries FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can view own weekly summaries"
    ON weekly_summaries FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own weekly summaries"
    ON weekly_summaries FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own weekly summaries"
    ON weekly_summaries FOR UPDATE
    USING (auth.uid() = user_id);

-- Service role can access all
CREATE POLICY "Service role full access daily"
    ON daily_summaries FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Service role full access weekly"
    ON weekly_summaries FOR ALL
    USING (auth.jwt() ->> 'role' = 'service_role');
