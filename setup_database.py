"""
Synki Database Setup Script
Creates all tables in Supabase using direct PostgreSQL connection
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env.local")
    exit(1)

# Extract project ref from URL
PROJECT_REF = SUPABASE_URL.split('//')[1].split('.')[0]

# Full SQL to execute
FULL_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- PROFILES TABLE
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Baby',
    email TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users can view own profile" ON profiles
        FOR SELECT USING (auth.uid() = id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users can update own profile" ON profiles
        FOR UPDATE USING (auth.uid() = id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users can insert own profile" ON profiles
        FOR INSERT WITH CHECK (auth.uid() = id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- MEMORIES TABLE
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

ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users can view own memories" ON memories
        FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users can update own memories" ON memories
        FOR UPDATE USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users can insert own memories" ON memories
        FOR INSERT WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Service role can manage all memories" ON memories
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- CHAT HISTORY TABLE
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    emotion TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_id ON chat_history(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_created_at ON chat_history(created_at DESC);

ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users can view own chat history" ON chat_history
        FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Users can insert own chat" ON chat_history
        FOR INSERT WITH CHECK (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Service role can manage all chats" ON chat_history
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- SESSIONS TABLE
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

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY "Users can view own sessions" ON sessions
        FOR SELECT USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE POLICY "Service role can manage all sessions" ON sessions
        FOR ALL USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- FUNCTIONS
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_memories_updated_at ON memories;
CREATE TRIGGER update_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated;
"""


def main():
    print("🚀 Synki Database Setup")
    print("=" * 50)
    print(f"📡 Project: {PROJECT_REF}")
    print()
    
    db_password = os.getenv('SUPABASE_DB_PASSWORD')
    
    if not db_password:
        print("⚠️  SUPABASE_DB_PASSWORD not found in .env.local")
        print()
        print("📝 To get your database password:")
        print(f"   1. Go to: https://supabase.com/dashboard/project/{PROJECT_REF}/settings/database")
        print("   2. Scroll to 'Database password' section")
        print("   3. Click 'Reset database password' or use existing")
        print("   4. Add to .env.local: SUPABASE_DB_PASSWORD=your_password_here")
        print()
        print("🔄 Or run SQL manually:")
        print(f"   1. Go to: https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")
        print("   2. Copy contents of: supabase_schema.sql")
        print("   3. Click 'Run'")
        return
    
    try:
        import psycopg2
        from urllib.parse import quote_plus
        
        # URL encode the password to handle special characters
        encoded_password = quote_plus(db_password)
        
        # Try different connection methods
        regions = ['ap-northeast-2', 'us-east-1', 'us-west-1', 'ap-south-1', 'eu-west-1', 'ap-southeast-1']
        
        conn = None
        for region in regions:
            try:
                conn_string = f"postgresql://postgres.{PROJECT_REF}:{encoded_password}@aws-0-{region}.pooler.supabase.com:5432/postgres?sslmode=require"
                print(f"   Trying region: {region}...")
                conn = psycopg2.connect(conn_string, connect_timeout=5)
                print(f"   ✅ Connected via {region}!")
                break
            except Exception as e:
                if "Tenant or user not found" in str(e) or "could not translate" in str(e):
                    continue
                else:
                    print(f"   ⚠️ {region}: {str(e)[:50]}")
        
        if not conn:
            # Try direct connection
            try:
                conn_string = f"postgresql://postgres:{encoded_password}@db.{PROJECT_REF}.supabase.co:5432/postgres?sslmode=require"
                print("   Trying direct connection...")
                conn = psycopg2.connect(conn_string, connect_timeout=10)
                print("   ✅ Connected directly!")
            except Exception as e:
                raise Exception(f"All connection methods failed: {e}")
        
        conn.autocommit = True
        cur = conn.cursor()
        
        print()
        print("📋 Executing SQL schema...")
        
        # Execute the full SQL
        cur.execute(FULL_SQL)
        
        print("✅ SQL executed successfully!")
        print()
        
        # Verify tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        
        tables = cur.fetchall()
        print("📋 Tables in database:")
        for table in tables:
            print(f"   ✅ {table[0]}")
        
        cur.close()
        conn.close()
        
        print()
        print("🎉 Database setup complete!")
        
    except ImportError:
        print("❌ psycopg2 not installed. Run: uv add psycopg2-binary")
    except Exception as e:
        error_msg = str(e)
        if "password authentication failed" in error_msg:
            print("❌ Invalid database password. Please check SUPABASE_DB_PASSWORD")
        elif "could not connect" in error_msg:
            print("❌ Could not connect to database. Check your network connection.")
        else:
            print(f"❌ Error: {e}")
        print()
        print("🔄 Alternative: Run SQL manually")
        print(f"   1. Go to: https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")
        print("   2. Copy contents of: supabase_schema.sql")
        print("   3. Click 'Run'")


if __name__ == "__main__":
    main()
