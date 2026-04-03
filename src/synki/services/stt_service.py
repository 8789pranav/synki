"""
STT Service

Speech-to-Text service abstraction with Deepgram implementation.
Supports streaming STT with interim results for low-latency transcription.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Callable

import structlog

from ..config import settings
from ..models import TranscriptEvent

logger = structlog.get_logger(__name__)


class STTService(ABC):
    """Abstract base class for STT services."""
    
    @abstractmethod
    async def start_stream(
        self,
        session_id: str,
        on_transcript: Callable[[TranscriptEvent], None],
    ) -> None:
        """Start a streaming STT session."""
        pass
    
    @abstractmethod
    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio data to the STT service."""
        pass
    
    @abstractmethod
    async def stop_stream(self) -> None:
        """Stop the streaming STT session."""
        pass


class DeepgramSTTService(STTService):
    """
    Deepgram streaming STT implementation.
    
    Features:
    - Real-time streaming transcription
    - Interim results for low-latency partial transcripts
    - Endpointing for speech detection
    - Multi-language support (Hindi/English)
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        language: str | None = None,
    ):
        """
        Initialize Deepgram STT service.
        
        Args:
            api_key: Deepgram API key (defaults to settings)
            model: Deepgram model name (defaults to settings)
            language: Language code (defaults to settings)
        """
        self.api_key = api_key or settings.deepgram.api_key
        self.model = model or settings.deepgram.model
        self.language = language or settings.deepgram.language
        
        self._connection: Any = None
        self._session_id: str | None = None
        self._on_transcript: Callable[[TranscriptEvent], None] | None = None
        self._is_streaming = False
    
    async def start_stream(
        self,
        session_id: str,
        on_transcript: Callable[[TranscriptEvent], None],
    ) -> None:
        """
        Start a streaming STT session with Deepgram.
        
        Args:
            session_id: Session identifier for transcript events
            on_transcript: Callback for transcript events
        """
        from deepgram import DeepgramClient
        
        self._session_id = session_id
        self._on_transcript = on_transcript
        
        try:
            # Initialize Deepgram client
            client = DeepgramClient(self.api_key)
            
            # Create streaming connection with options
            self._connection = client.listen.live.v("1")
            
            # Configure options
            options = {
                "model": self.model,
                "language": self.language,
                "smart_format": settings.deepgram.smart_format,
                "interim_results": settings.deepgram.interim_results,
                "endpointing": settings.deepgram.endpointing_ms,
                "utterance_end_ms": 1000,
                "vad_events": True,
                "encoding": "linear16",
                "channels": 1,
                "sample_rate": 16000,
            }
            
            # Start the connection
            await self._connection.start(options)
            
            # Set up event handlers
            self._connection.on("Results", self._handle_transcript)
            self._connection.on("UtteranceEnd", self._handle_utterance_end)
            self._connection.on("Error", self._handle_error)
            
            self._is_streaming = True
            
            logger.info(
                "deepgram_stream_started",
                session_id=session_id,
                model=self.model,
                language=self.language,
            )
            
        except Exception as e:
            logger.error("deepgram_start_failed", error=str(e))
            raise
    
    async def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio data to Deepgram.
        
        Args:
            audio_data: Raw audio bytes (PCM 16-bit, 16kHz)
        """
        if not self._connection or not self._is_streaming:
            return
        
        try:
            await self._connection.send(audio_data)
        except Exception as e:
            logger.error("deepgram_send_failed", error=str(e))
    
    async def stop_stream(self) -> None:
        """Stop the Deepgram streaming session."""
        if self._connection:
            try:
                await self._connection.finish()
                self._is_streaming = False
                logger.info("deepgram_stream_stopped", session_id=self._session_id)
            except Exception as e:
                logger.error("deepgram_stop_failed", error=str(e))
            finally:
                self._connection = None
    
    def _handle_transcript(self, result: Any) -> None:
        """Handle transcript result from Deepgram."""
        if not self._on_transcript or not self._session_id:
            return
        
        try:
            # Extract transcript from result
            channel = result.channel
            if not channel or not channel.alternatives:
                return
            
            alternative = channel.alternatives[0]
            transcript = alternative.transcript
            
            if not transcript:
                return
            
            # Determine if this is a final result
            is_final = getattr(result, "is_final", False)
            speech_final = getattr(result, "speech_final", False)
            confidence = getattr(alternative, "confidence", 0.0)
            
            # Extract words if available
            words = []
            if hasattr(alternative, "words"):
                words = [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "confidence": w.confidence,
                    }
                    for w in alternative.words
                ]
            
            # Create transcript event
            event = TranscriptEvent(
                session_id=self._session_id,
                type="final_transcript" if is_final else "partial_transcript",
                text=transcript,
                is_final=is_final,
                speech_final=speech_final,
                confidence=confidence,
                words=words,
            )
            
            # Invoke callback
            self._on_transcript(event)
            
            logger.debug(
                "transcript_received",
                text_preview=transcript[:50],
                is_final=is_final,
                confidence=confidence,
            )
            
        except Exception as e:
            logger.error("transcript_handling_failed", error=str(e))
    
    def _handle_utterance_end(self, result: Any) -> None:
        """Handle utterance end event."""
        logger.debug("utterance_end_received", session_id=self._session_id)
    
    def _handle_error(self, error: Any) -> None:
        """Handle Deepgram error."""
        logger.error("deepgram_error", error=str(error))


class MockSTTService(STTService):
    """Mock STT service for testing."""
    
    def __init__(self):
        self._on_transcript: Callable[[TranscriptEvent], None] | None = None
        self._session_id: str | None = None
    
    async def start_stream(
        self,
        session_id: str,
        on_transcript: Callable[[TranscriptEvent], None],
    ) -> None:
        self._session_id = session_id
        self._on_transcript = on_transcript
        logger.info("mock_stt_started", session_id=session_id)
    
    async def send_audio(self, audio_data: bytes) -> None:
        pass  # Mock - no actual processing
    
    async def stop_stream(self) -> None:
        logger.info("mock_stt_stopped", session_id=self._session_id)
    
    async def simulate_transcript(self, text: str, is_final: bool = True) -> None:
        """Simulate receiving a transcript for testing."""
        if self._on_transcript and self._session_id:
            event = TranscriptEvent(
                session_id=self._session_id,
                type="final_transcript" if is_final else "partial_transcript",
                text=text,
                is_final=is_final,
                speech_final=is_final,
                confidence=0.95,
            )
            self._on_transcript(event)
