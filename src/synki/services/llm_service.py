"""
LLM Service

Language Model service abstraction with OpenAI implementation.
Supports streaming text generation for low-latency responses.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import structlog

from ..config import settings
from ..models import EmotionState, LLMInputPacket, ResponseStrategy

logger = structlog.get_logger(__name__)


class LLMService(ABC):
    """Abstract base class for LLM services."""
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a non-streaming response."""
        pass
    
    @abstractmethod
    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response."""
        pass


class OpenAILLMService(LLMService):
    """
    OpenAI LLM implementation with streaming support.
    
    Features:
    - Streaming text generation for low-latency TTS feeding
    - Persona-aware system prompts
    - Context window management
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize OpenAI LLM service.
        
        Args:
            api_key: OpenAI API key (defaults to settings)
            model: Model name (defaults to settings)
        """
        self.api_key = api_key or settings.openai.api_key
        self.model = model or settings.openai.model
        self.max_tokens = settings.openai.max_tokens
        self.temperature = settings.openai.temperature
        
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client
    
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Generate a non-streaming response.
        
        Args:
            system_prompt: System instructions
            user_message: User's message
            context: Optional conversation history
            
        Returns:
            Generated response text
        """
        client = self._get_client()
        
        messages = self._build_messages(system_prompt, user_message, context)
        
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            text = response.choices[0].message.content or ""
            
            logger.info(
                "llm_response_generated",
                model=self.model,
                tokens_used=response.usage.total_tokens if response.usage else 0,
                response_preview=text[:50],
            )
            
            return text
            
        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            raise
    
    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        """
        Generate a streaming response.
        
        Yields text chunks as they are generated, enabling
        immediate TTS processing before full response is complete.
        
        Args:
            system_prompt: System instructions
            user_message: User's message
            context: Optional conversation history
            
        Yields:
            Text chunks as they are generated
        """
        client = self._get_client()
        
        messages = self._build_messages(system_prompt, user_message, context)
        
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )
            
            full_response = ""
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    full_response += text
                    yield text
            
            logger.info(
                "llm_stream_completed",
                model=self.model,
                response_length=len(full_response),
                response_preview=full_response[:50],
            )
            
        except Exception as e:
            logger.error("llm_stream_failed", error=str(e))
            raise
    
    async def generate_from_packet(
        self,
        packet: LLMInputPacket,
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """
        Generate response from an LLMInputPacket.
        
        Args:
            packet: Prepared LLM input packet
            system_prompt: System prompt from persona engine
            
        Yields:
            Text chunks for streaming TTS
        """
        # Handle quick/cached responses
        if packet.style == "quick_response":
            yield packet.response_goal
            return
        
        # Build user message with context
        user_parts = []
        
        if packet.recent_context:
            user_parts.append("Recent conversation:")
            for line in packet.recent_context[-3:]:
                user_parts.append(f"  {line}")
            user_parts.append("")
        
        user_parts.append(f"User just said: \"{packet.user_text}\"")
        user_parts.append("")
        user_parts.append(f"Response goal: {packet.response_goal}")
        
        user_message = "\n".join(user_parts)
        
        async for chunk in self.generate_stream(system_prompt, user_message):
            yield chunk
    
    def _build_messages(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Build messages array for API call."""
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add context messages
        if context:
            messages.extend(context)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        return messages


class MockLLMService(LLMService):
    """Mock LLM service for testing."""
    
    def __init__(self, response: str = "Hii! Main hoon na, bata kya hua?"):
        self.response = response
    
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> str:
        await asyncio.sleep(0.1)  # Simulate latency
        return self.response
    
    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
        context: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        # Simulate streaming by yielding word by word
        words = self.response.split()
        for i, word in enumerate(words):
            await asyncio.sleep(0.05)  # Simulate token generation
            yield word + (" " if i < len(words) - 1 else "")


class SentenceBuffer:
    """
    Buffer that accumulates text and yields complete sentences.
    
    Useful for feeding TTS with natural sentence boundaries
    rather than arbitrary token chunks.
    """
    
    SENTENCE_ENDINGS = {'.', '!', '?', '।'}  # Include Hindi danda
    
    def __init__(self, min_chars: int = 10):
        """
        Initialize sentence buffer.
        
        Args:
            min_chars: Minimum characters before checking for sentence end
        """
        self.buffer = ""
        self.min_chars = min_chars
    
    def add(self, text: str) -> list[str]:
        """
        Add text and return any complete sentences.
        
        Args:
            text: Text chunk to add
            
        Returns:
            List of complete sentences (may be empty)
        """
        self.buffer += text
        sentences = []
        
        # Look for sentence endings
        while len(self.buffer) >= self.min_chars:
            # Find earliest sentence ending
            earliest_end = -1
            for ending in self.SENTENCE_ENDINGS:
                idx = self.buffer.find(ending)
                if idx != -1 and (earliest_end == -1 or idx < earliest_end):
                    earliest_end = idx
            
            if earliest_end == -1:
                break
            
            # Extract sentence
            sentence = self.buffer[:earliest_end + 1].strip()
            self.buffer = self.buffer[earliest_end + 1:].lstrip()
            
            if sentence:
                sentences.append(sentence)
        
        return sentences
    
    def flush(self) -> str | None:
        """
        Flush remaining buffer content.
        
        Returns:
            Remaining text or None if empty
        """
        if self.buffer.strip():
            result = self.buffer.strip()
            self.buffer = ""
            return result
        return None
