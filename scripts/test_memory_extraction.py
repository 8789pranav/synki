"""
Test script to verify memory extraction and database saving.

Run with: uv run python scripts/test_memory_extraction.py
"""

import asyncio
from datetime import datetime

# Test the extraction and memory components
from synki.orchestrator.entity_extractor import EntityExtractor
from synki.orchestrator.proactive_memory import (
    ProactiveMemoryPrompter, 
    MemoryTopic,
    PendingMemoryQuery,
)
from synki.orchestrator.layered_memory import (
    LayeredMemoryService,
    MemoryFact,
    MemoryCategory,
    Entity,
    EntityType,
)


def test_entity_extraction():
    """Test entity extraction from various user messages."""
    print("\n" + "="*60)
    print("TESTING ENTITY EXTRACTION")
    print("="*60)
    
    extractor = EntityExtractor()
    
    test_messages = [
        "I watched Inception yesterday, it was amazing",
        "Mujhe Paracetamol leni hai roz subah",
        "My friend Rahul works at Google",
        "I love eating biryani and pizza",
        "Doctor ne Crocin di hai fever ke liye",
        "Meeting hai 3pm ko office mein",
        "Mera birthday 15th March ko hai",
        "I have allergy to peanuts",
        "My dog Tommy is so cute",
        "Main roz 7 baje gym jaata hoon",
    ]
    
    for msg in test_messages:
        print(f"\n📝 Input: \"{msg}\"")
        
        # Extract entities
        entities = extractor.extract_entities(msg)
        if entities:
            print("   🎯 Entities found:")
            for e in entities:
                print(f"      - {e.type.value}: {e.value} (confidence: {e.confidence})")
        else:
            print("   ❌ No entities extracted")
        
        # Extract memory facts
        facts = extractor.extract_memory_facts(msg)
        if facts:
            print("   💾 Facts found:")
            for f in facts:
                print(f"      - [{f.category.value}] {f.fact_key}: {f.fact_value}")
        
        # Check for entity references
        refs = extractor.detect_entity_references(msg)
        if refs:
            print("   🔗 Entity references detected:")
            for ref_type, pattern in refs:
                print(f"      - References {ref_type.value}")
        
        # Classify intent
        intent = extractor.classify_message_intent(msg)
        if intent["is_sharing_info"]:
            print(f"   ℹ️  User is sharing info (action: {intent['memory_action']})")
        if intent["is_referencing"]:
            print(f"   🔙 User is referencing past")


def test_proactive_memory():
    """Test proactive memory detection and prompting."""
    print("\n" + "="*60)
    print("TESTING PROACTIVE MEMORY PROMPTS")
    print("="*60)
    
    prompter = ProactiveMemoryPrompter()
    
    test_messages = [
        ("Mujhe medicine leni hai", "session1"),
        ("I have a meeting today", "session2"),
        ("My birthday is coming soon", "session3"),
        ("I take Aspirin daily at 8am", "session4"),  # Complete - no prompt expected
        ("Mujhe allergy hai", "session5"),
        ("I have a pet", "session6"),
        ("I go to gym", "session7"),
        ("I can't sleep properly", "session8"),
        ("Doctor ne dawai di hai", "session9"),
    ]
    
    for msg, session_id in test_messages:
        print(f"\n📝 Input: \"{msg}\"")
        
        # Detect topics
        topics = prompter.detect_memory_topics(msg)
        if topics:
            print(f"   📌 Topics detected: {[t.value for t in topics]}")
        
        # Check for incomplete info
        prompt = prompter.analyze_for_memory_prompts(msg, session_id)
        if prompt:
            print(f"   ❓ Follow-up needed!")
            print(f"      Topic: {prompt.topic.value}")
            print(f"      Missing: {prompt.missing_field}")
            print(f"      Question: {prompt.question_hinglish}")
            
            # Format for response
            formatted = prompter.format_question_for_response(prompt)
            print(f"      Formatted: \"{formatted}\"")
        else:
            print(f"   ✅ Info complete, no follow-up needed")


def test_pending_response_flow():
    """Test the full flow of asking and receiving answers."""
    print("\n" + "="*60)
    print("TESTING PENDING RESPONSE FLOW")
    print("="*60)
    
    prompter = ProactiveMemoryPrompter()
    session_id = "test_flow_session"
    
    # Step 1: User mentions medicine without name
    print("\n📝 User: \"Mujhe dawai leni hai roz\"")
    prompt = prompter.analyze_for_memory_prompts("Mujhe dawai leni hai roz", session_id)
    
    if prompt:
        print(f"   🤖 Bot asks: \"{prompt.question_hinglish}\"")
        print(f"   📋 Missing field: {prompt.missing_field}")
        
        # Check pending
        pending = prompter.get_pending_queries(session_id)
        print(f"   📋 Pending queries: {len(pending)}")
        
        # Step 2: User responds - test different responses
        test_responses = [
            "Crocin tablet leti hoon",
            "Paracetamol",
            "8 baje subah",
            "morning mein leti hoon",
        ]
        
        for response in test_responses:
            # Reset pending for each test
            prompter._pending_queries[session_id] = [PendingMemoryQuery(
                topic=prompt.topic,
                missing_field=prompt.missing_field,
                question_asked=prompt.question,
                context={"original_context": "Mujhe dawai leni hai roz"}
            )]
            
            print(f"\n📝 User responds: \"{response}\"")
            result = prompter._check_pending_response(response, session_id)
            
            if result:
                print(f"   ✅ Answer captured!")
                print(f"      Field: {result.missing_field}")
                print(f"      Answer: {result.context.get('answer')}")
            else:
                print("   ❌ Answer not captured")
    else:
        print("   ❌ No prompt generated")


async def test_layered_memory_save():
    """Test saving to layered memory (in-memory without DB)."""
    print("\n" + "="*60)
    print("TESTING LAYERED MEMORY SAVE (IN-MEMORY)")
    print("="*60)
    
    # Create service without DB connection (will use in-memory)
    memory_service = LayeredMemoryService()
    
    user_id = "test_user_123"
    session_id = "test_session_456"
    
    # Test saving a memory fact
    print("\n💾 Saving memory fact...")
    fact = MemoryFact(
        category=MemoryCategory.MEDICAL,
        fact_key="medicine_name",
        fact_value="Crocin",
        confidence=0.9,
        source="proactive_prompt"
    )
    await memory_service.save_memory_fact(user_id, fact)
    print(f"   Saved: [{fact.category.value}] {fact.fact_key} = {fact.fact_value}")
    
    # Test saving entity to session
    print("\n🎯 Adding entity to session...")
    entity = Entity(
        type=EntityType.MEDICINE,
        value="Crocin",
        confidence=0.9
    )
    await memory_service.add_entity_to_session(user_id, session_id, entity)
    print(f"   Added: {entity.type.value} = {entity.value}")
    
    # Retrieve session state
    print("\n📖 Retrieving session state...")
    state = await memory_service.get_session_state(user_id, session_id)
    print(f"   Session ID: {state.session_id}")
    print(f"   User ID: {state.user_id}")
    print(f"   Active entities: {len(state.active_entities)}")
    for key, ent in state.active_entities.items():
        print(f"      - {key}: {ent.value}")
    
    # Add a message
    print("\n💬 Adding message to session...")
    await memory_service.add_message_to_session(
        user_id, session_id, "user", "Mujhe Crocin leni hai", "neutral"
    )
    await memory_service.add_message_to_session(
        user_id, session_id, "assistant", "Okay baby, Crocin kitne baje leni hai?"
    )
    
    state = await memory_service.get_session_state(user_id, session_id)
    print(f"   Messages in session: {len(state.recent_messages)}")
    for msg in state.recent_messages:
        print(f"      [{msg['role']}]: {msg['content'][:50]}...")


async def test_with_supabase():
    """Test with actual Supabase connection if configured."""
    print("\n" + "="*60)
    print("TESTING WITH SUPABASE (if configured)")
    print("="*60)
    
    try:
        from synki.config import settings
        
        if not settings.supabase.url or not settings.supabase.service_key:
            print("   ⚠️  Supabase not configured. Skipping DB test.")
            print("   Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
            return
        
        from supabase import create_client, Client
        
        supabase: Client = create_client(
            settings.supabase.url,
            settings.supabase.service_key
        )
        
        print(f"   ✅ Connected to Supabase: {settings.supabase.url[:30]}...")
        
        # Test if memory tables exist
        print("\n   Checking memory tables...")
        
        tables_to_check = [
            "user_profiles",
            "memory_facts", 
            "conversation_threads",
            "thread_entities",
            "memory_embeddings",
            "memory_summaries",
            "important_events",
            "anti_repetition_log"
        ]
        
        for table in tables_to_check:
            try:
                result = supabase.table(table).select("*").limit(1).execute()
                print(f"      ✅ {table}: exists")
            except Exception as e:
                print(f"      ❌ {table}: {str(e)[:50]}")
        
        # Test inserting a memory fact
        print("\n   Testing memory fact insert...")
        test_user_id = "test_user_" + datetime.now().strftime("%Y%m%d%H%M%S")
        
        try:
            result = supabase.table("memory_facts").insert({
                "user_id": test_user_id,
                "category": "medical",
                "fact_key": "test_medicine",
                "fact_value": "TestDrug",
                "confidence": 0.9,
                "source": "test_script",
                "mention_count": 1
            }).execute()
            print(f"      ✅ Insert successful: {result.data}")
            
            # Clean up
            supabase.table("memory_facts").delete().eq(
                "user_id", test_user_id
            ).execute()
            print("      🧹 Test data cleaned up")
            
        except Exception as e:
            print(f"      ❌ Insert failed: {e}")
            print("      📋 Make sure to run supabase_memory_schema.sql first!")
        
    except ImportError:
        print("   ⚠️  Supabase client not installed. Run: uv pip install supabase")
    except Exception as e:
        print(f"   ❌ Error: {e}")


def main():
    """Run all tests."""
    print("\n" + "🧠"*30)
    print("  SYNKI MEMORY EXTRACTION & SAVE TEST")
    print("🧠"*30)
    
    # Test 1: Entity extraction
    test_entity_extraction()
    
    # Test 2: Proactive memory prompts
    test_proactive_memory()
    
    # Test 3: Pending response flow
    test_pending_response_flow()
    
    # Test 4: Layered memory save (in-memory)
    asyncio.run(test_layered_memory_save())
    
    # Test 5: Supabase connection (if configured)
    asyncio.run(test_with_supabase())
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
