"""
TTS Service

Text-to-Speech service abstraction with Cartesia implementation.
Supports streaming TTS with WebSocket contexts for incremental input.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from uuid import uuid4

import structlog

from ..config import settings
from ..models import TTSRequest

logger = structlog.get_logger(__name__)


class TTSService(ABC):
    """Abstract base class for TTS services."""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to TTS service."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to TTS service."""
        pass
    
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
    ) -> bytes:
        """Synthesize text to audio (non-streaming)."""
        pass
    
    @abstractmethod
    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Synthesize streaming text to streaming audio."""
        pass


class CartesiaTTSService(TTSService):
    """
    Cartesia streaming TTS implementation.
    
    Features:
    - WebSocket connection for low-latency streaming
    - Context-based input streaming (incremental text)
    - Seamless prosody between text chunks
    - Multiple voice support
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model: str | None = None,
    ):
        """
        Initialize Cartesia TTS service.
        
        Args:
            api_key: Cartesia API key (defaults to settings)
            voice_id: Default voice ID (defaults to settings)
            model: TTS model name (defaults to settings)
        """
        self.api_key = api_key or settings.cartesia.api_key
        self.voice_id = voice_id or settings.cartesia.voice_id
        self.model = model or settings.cartesia.model
        self.sample_rate = settings.cartesia.sample_rate
        self.encoding = settings.cartesia.encoding
        
        self._client: Any = None
        self._connection: Any = None
        self._is_connected = False
    
    async def connect(self) -> None:
        """
        Establish WebSocket connection to Cartesia.
        """
        from cartesia import AsyncCartesia
        
        try:
            self._client = AsyncCartesia(api_key=self.api_key)
            self._is_connected = True
            
            logger.info(
                "cartesia_connected",
                model=self.model,
                voice_id=self.voice_id,
            )
            
        except Exception as e:
            logger.error("cartesia_connect_failed", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Close Cartesia connection."""
        if self._connection:
            try:
                await self._connection.close()
            except Exception as e:
                logger.error("cartesia_disconnect_failed", error=str(e))
            finally:
                self._connection = None
        
        self._is_connected = False
        logger.info("cartesia_disconnected")
    
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
    ) -> bytes:
        """
        Synthesize text to audio (non-streaming).
        
        Args:
            text: Text to synthesize
            voice_id: Optional voice override
            
        Returns:
            Audio bytes
        """
        if not self._client:
            await self.connect()
        
        voice = voice_id or self.voice_id
        
        try:
            audio_data = b""
            
            async for chunk in self._client.tts.sse(
                model_id=self.model,
                transcript=text,
                voice={"mode": "id", "id": voice},
                output_format={
                    "container": "raw",
                    "encoding": self.encoding,
                    "sample_rate": self.sample_rate,
                },
            ):
                if hasattr(chunk, "audio"):
                    audio_data += chunk.audio
            
            logger.info(
                "tts_synthesized",
                text_preview=text[:30],
                audio_bytes=len(audio_data),
            )
            
            return audio_data
            
        except Exception as e:
            logger.error("tts_synthesis_failed", error=str(e))
            raise
    
    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """
        Synthesize streaming text to streaming audio using Cartesia contexts.
        
        This is the key low-latency feature: as LLM generates text tokens,
        we feed them to Cartesia incrementally, and audio chunks start
        streaming back before the full text is available.
        
        Args:
            text_stream: Async iterator of text chunks
            voice_id: Optional voice override
            
        Yields:
            Audio bytes as they are generated
        """
        if not self._client:
            await self.connect()
        
        voice = voice_id or self.voice_id
        context_id = f"ctx_{uuid4().hex[:12]}"
        
        try:
            # Connect WebSocket
            async with self._client.tts.websocket() as ws:
                # Create context for this synthesis
                ctx = ws.context(
                    model_id=self.model,
                    voice={"mode": "id", "id": voice},
                    output_format={
                        "container": "raw",
                        "encoding": self.encoding,
                        "sample_rate": self.sample_rate,
                    },
                )
                
                # Task to send text chunks
                async def send_text():
                    try:
                        async for text_chunk in text_stream:
                            if text_chunk:
                                ctx.push(text_chunk)
                    finally:
                        ctx.no_more_inputs()
                
                # Start sending in background
                send_task = asyncio.create_task(send_text())
                
                # Yield audio chunks as they arrive
                try:
                    async for response in ctx.receive():
                        if response.type == "chunk" and response.audio:
                            yield response.audio
                        elif response.type == "done":
                            break
                finally:
                    # Ensure send task completes
                    if not send_task.done():
                        send_task.cancel()
                        try:
                            await send_task
                        except asyncio.CancelledError:
                            pass
                
                logger.info(
                    "tts_stream_completed",
                    context_id=context_id,
                )
                
        except Exception as e:
            logger.error("tts_stream_failed", error=str(e))
            raise
    
    async def synthesize_with_sentences(
        self,
        sentences: list[str],
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        """
        Synthesize multiple sentences maintaining prosody.
        
        Args:
            sentences: List of sentences to synthesize
            voice_id: Optional voice override
            
        Yields:
            Audio bytes
        """
        if not sentences:
            return
        
        if not self._client:
            await self.connect()
        
        voice = voice_id or self.voice_id
        
        try:
            async with self._client.tts.websocket() as ws:
                ctx = ws.context(
                    model_id=self.model,
                    voice={"mode": "id", "id": voice},
                    output_format={
                        "container": "raw",
                        "encoding": self.encoding,
                        "sample_rate": self.sample_rate,
                    },
                )
                
                # Push all sentences
                for i, sentence in enumerate(sentences):
                    ctx.push(sentence)
                
                ctx.no_more_inputs()
                
                # Receive audio
                async for response in ctx.receive():
                    if response.type == "chunk" and response.audio:
                        yield response.audio
                    elif response.type == "done":
                        break
                
        except Exception as e:
            logger.error("tts_sentences_failed", error=str(e))
            raise


class MockTTSService(TTSService):
    """Mock TTS service for testing."""
    
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self._is_connected = False
    
    async def connect(self) -> None:
        self._is_connected = True
        logger.info("mock_tts_connected")
    
    async def disconnect(self) -> None:
        self._is_connected = False
        logger.info("mock_tts_disconnected")
    
    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
    ) -> bytes:
        # Return silence of appropriate duration
        # Roughly 100ms per word
        words = len(text.split())
        duration_samples = int(words * 0.1 * self.sample_rate)
        return bytes(duration_samples * 4)  # f32le = 4 bytes per sample
    
    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        voice_id: str | None = None,
    ) -> AsyncIterator[bytes]:
        # Consume text and yield mock audio chunks
        async for text in text_stream:
            if text:
                # Yield small audio chunk for each text chunk
                await asyncio.sleep(0.02)  # Simulate processing
                chunk_samples = int(0.05 * self.sample_rate)  # 50ms chunks
                yield bytes(chunk_samples * 4)


class AudioBuffer:
    """
    Buffer for accumulating audio chunks before publishing.
    
    Useful for smoothing out audio delivery and ensuring
    minimum chunk sizes for playback.
    """
    
    def __init__(
        self,
        min_chunk_ms: int = 50,
        sample_rate: int = 24000,
        bytes_per_sample: int = 4,  # f32le
    ):
        """
        Initialize audio buffer.
        
        Args:
            min_chunk_ms: Minimum chunk duration in milliseconds
            sample_rate: Audio sample rate
            bytes_per_sample: Bytes per sample (4 for f32le)
        """
        self.min_chunk_bytes = int(
            min_chunk_ms / 1000 * sample_rate * bytes_per_sample
        )
        self.buffer = b""
    
    def add(self, audio: bytes) -> list[bytes]:
        """
        Add audio and return any chunks that meet minimum size.
        
        Args:
            audio: Audio bytes to add
            
        Returns:
            List of audio chunks (may be empty)
        """
        self.buffer += audio
        chunks = []
        
        while len(self.buffer) >= self.min_chunk_bytes:
            chunks.append(self.buffer[:self.min_chunk_bytes])
            self.buffer = self.buffer[self.min_chunk_bytes:]
        
        return chunks
    
    def flush(self) -> bytes | None:
        """
        Flush remaining buffer content.
        
        Returns:
            Remaining audio or None if empty
        """
        if self.buffer:
            result = self.buffer
            self.buffer = b""
            return result
        return None
