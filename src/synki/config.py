"""
Synki Configuration Module

Centralized configuration using Pydantic Settings.
"""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env.local BEFORE defining settings classes
load_dotenv(".env.local")


class LiveKitSettings(BaseSettings):
    """LiveKit connection settings."""
    
    model_config = SettingsConfigDict(env_prefix="LIVEKIT_")
    
    url: str = Field(default="wss://localhost:7880", description="LiveKit server URL")
    api_key: str = Field(default="", description="LiveKit API key")
    api_secret: str = Field(default="", description="LiveKit API secret")


class DeepgramSettings(BaseSettings):
    """Deepgram STT settings."""
    
    model_config = SettingsConfigDict(env_prefix="DEEPGRAM_")
    
    api_key: str = Field(default="", description="Deepgram API key")
    model: str = Field(default="nova-3", description="Deepgram model name")
    language: str = Field(default="hi", description="Primary language code")
    interim_results: bool = Field(default=True, description="Enable interim transcripts")
    endpointing_ms: int = Field(default=300, description="Silence detection in ms")
    smart_format: bool = Field(default=True, description="Enable smart formatting")


class OpenAISettings(BaseSettings):
    """OpenAI LLM settings."""
    
    model_config = SettingsConfigDict(env_prefix="OPENAI_")
    
    api_key: str = Field(default="", description="OpenAI API key")
    model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    max_tokens: int = Field(default=100, description="Max response tokens")
    temperature: float = Field(default=0.8, description="Response creativity")
    stream: bool = Field(default=True, description="Enable streaming responses")


class CartesiaSettings(BaseSettings):
    """Cartesia TTS settings."""
    
    model_config = SettingsConfigDict(env_prefix="CARTESIA_")
    
    api_key: str = Field(default="", description="Cartesia API key")
    voice_id: str = Field(default="", description="Selected voice ID")
    model: str = Field(default="sonic-3", description="Cartesia TTS model")
    sample_rate: int = Field(default=24000, description="Audio sample rate")
    encoding: str = Field(default="pcm_f32le", description="Audio encoding format")


class RedisSettings(BaseSettings):
    """Redis connection settings for memory/state."""
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    session_ttl: int = Field(default=3600, description="Session TTL in seconds")
    memory_ttl: int = Field(default=86400 * 30, description="Long-term memory TTL (30 days)")


class SupabaseSettings(BaseSettings):
    """Supabase connection settings for database."""
    
    model_config = SettingsConfigDict(env_prefix="SUPABASE_")
    
    url: str = Field(default="", description="Supabase project URL")
    key: str = Field(default="", description="Supabase anon/public key")
    service_key: str = Field(default="", description="Supabase service role key")


class PersonaSettings(BaseSettings):
    """Persona configuration settings."""
    
    model_config = SettingsConfigDict(env_prefix="PERSONA_")
    
    default_mode: Literal["girlfriend", "friend", "mentor"] = Field(
        default="girlfriend", 
        description="Default persona mode"
    )
    language_style: Literal["hinglish", "hindi", "english"] = Field(
        default="hinglish",
        description="Default language style"
    )
    emoji_level: Literal["none", "low", "medium", "high"] = Field(
        default="low",
        description="Emoji usage level"
    )


class AppSettings(BaseSettings):
    """Main application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    agent_name: str = Field(default="synki-companion", description="Agent identifier")
    log_level: str = Field(default="INFO", description="Logging level")
    debug_mode: bool = Field(default=False, description="Debug mode flag")
    preferred_tts: str = Field(default="openai", description="Preferred TTS provider: openai, cartesia, deepgram")
    
    # Nested settings
    livekit: LiveKitSettings = Field(default_factory=LiveKitSettings)
    deepgram: DeepgramSettings = Field(default_factory=DeepgramSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    cartesia: CartesiaSettings = Field(default_factory=CartesiaSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    persona: PersonaSettings = Field(default_factory=PersonaSettings)


@lru_cache
def get_settings() -> AppSettings:
    """Get cached application settings."""
    return AppSettings()


# Export settings instance
settings = get_settings()
