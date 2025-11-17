"""
Text-to-speech generation using ElevenLabs API.

This module handles conversion of text commentary to audio.
"""

import base64
import time
from typing import Optional
from elevenlabs import ElevenLabs


class TTSGenerator:
    """
    Handles text-to-speech generation using ElevenLabs API.
    """
    
    def __init__(self, api_key: str, default_voice_id: str = "nrD2uNU2IUYtedZegcGx"):
        """
        Initialize TTS generator.
        
        Args:
            api_key: ElevenLabs API key
            default_voice_id: Default voice ID to use
        """
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required")
        
        self.client = ElevenLabs(api_key=api_key)
        self.default_voice_id = default_voice_id
    
    def generate_audio(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: str = "eleven_multilingual_v2",
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> str:
        """
        Generate TTS audio and return as base64 string.

        Args:
            text: The text to convert to speech
            voice_id: The ElevenLabs voice ID to use (uses default if None)
            model_id: The model to use for generation
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (in seconds)

        Returns:
            Base64 encoded audio data (empty string on error)
        """
        voice = voice_id or self.default_voice_id

        for attempt in range(max_retries):
            try:
                # Generate audio using ElevenLabs API
                audio_generator = self.client.text_to_speech.convert(
                    voice_id=voice,
                    text=text,
                    model_id=model_id
                )

                # Collect all audio chunks
                audio_bytes = b''
                for chunk in audio_generator:
                    audio_bytes += chunk

                # Convert to base64
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                return audio_base64

            except Exception as e:
                error_str = str(e)
                is_quota_error = 'quota' in error_str.lower() or '401' in error_str
                is_rate_limit = 'rate' in error_str.lower() or '429' in error_str

                # Log the error
                print(f"[WARN] TTS generation failed for text: {text[:50]}...")
                print(f"   Error: {error_str}")

                # Check if this is a quota or rate limit error
                if is_quota_error:
                    print(f"   [QUOTA ERROR] ElevenLabs API quota exceeded!")
                    print(f"   Please add more credits to your ElevenLabs account or wait for quota reset.")
                    return ""  # Don't retry quota errors

                # Retry logic for transient errors
                if attempt < max_retries - 1 and (is_rate_limit or 'timeout' in error_str.lower()):
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    print(f"   Retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    continue

                # If we've exhausted retries or it's a permanent error, return empty
                return ""

        return ""
    
    def generate_batch(
        self,
        texts: list[str],
        voice_id: Optional[str] = None
    ) -> list[str]:
        """
        Generate TTS audio for multiple texts.
        
        Args:
            texts: List of texts to convert to speech
            voice_id: The ElevenLabs voice ID to use (uses default if None)
        
        Returns:
            List of base64 encoded audio data
        """
        results = []
        for i, text in enumerate(texts):
            print(f"Generating TTS audio {i+1}/{len(texts)}...")
            audio = self.generate_audio(text, voice_id)
            results.append(audio)
        return results

