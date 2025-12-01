"""
Text-to-speech generation using ElevenLabs API with dual commentator support.

This module handles conversion of text commentary to audio with different voices
for two commentators.
"""

import base64
import time
from typing import Optional, Dict
from elevenlabs import ElevenLabs


class TTSGenerator:
    """
    Handles text-to-speech generation using ElevenLabs API with support for multiple voices.
    """
    
    # Default voice mappings for commentators
    DEFAULT_VOICES = {
        "COMMENTATOR_1": "nrD2uNU2IUYtedZegcGx",  # Lead commentator voice
        "COMMENTATOR_2": "pNInz6obpgDQGcFmaJgB",  # Analyst commentator voice
    }
    
    def __init__(
        self, 
        api_key: str, 
        voice_mapping: Optional[Dict[str, str]] = None
    ):
        """
        Initialize TTS generator with dual voice support.
        
        Args:
            api_key: ElevenLabs API key
            voice_mapping: Optional custom voice mapping for commentators
                          Format: {"COMMENTATOR_1": "voice_id_1", "COMMENTATOR_2": "voice_id_2"}
                          If not provided, uses default voices
        """
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is required")
        
        self.client = ElevenLabs(api_key=api_key)
        
        # Use custom mapping or default voices
        self.voice_mapping = voice_mapping or self.DEFAULT_VOICES.copy()
        
        print(f"[TTS] Initialized with voice mapping:")
        print(f"  COMMENTATOR_1: {self.voice_mapping['COMMENTATOR_1']}")
        print(f"  COMMENTATOR_2: {self.voice_mapping['COMMENTATOR_2']}")
    
    def get_voice_for_speaker(self, speaker: str) -> str:
        """
        Get the appropriate voice ID for a given speaker.
        
        Args:
            speaker: Speaker identifier (COMMENTATOR_1 or COMMENTATOR_2)
            
        Returns:
            Voice ID string
            
        Raises:
            ValueError: If speaker is not recognized
        """
        if speaker not in self.voice_mapping:
            raise ValueError(
                f"Unknown speaker: {speaker}. "
                f"Must be one of: {list(self.voice_mapping.keys())}"
            )
        return self.voice_mapping[speaker]
    
    def generate_audio(
        self,
        text: str,
        speaker: str,
        model_id: str = "eleven_multilingual_v2",
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> str:
        """
        Generate TTS audio for a specific speaker and return as base64 string.

        Args:
            text: The text to convert to speech
            speaker: The speaker identifier (COMMENTATOR_1 or COMMENTATOR_2)
            model_id: The model to use for generation
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (in seconds)

        Returns:
            Base64 encoded audio data (empty string on error)
        """
        # Get the appropriate voice for this speaker
        voice_id = self.get_voice_for_speaker(speaker)
        
        print(f"[TTS] Generating audio for {speaker} with voice {voice_id[:8]}...")

        for attempt in range(max_retries):
            try:
                # Generate audio using ElevenLabs API
                audio_generator = self.client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=text,
                    model_id=model_id
                )

                # Collect all audio chunks
                audio_bytes = b''
                for chunk in audio_generator:
                    audio_bytes += chunk

                # Convert to base64
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                print(f"[TTS] Successfully generated {len(audio_base64)} bytes for {speaker}")
                return audio_base64

            except Exception as e:
                error_str = str(e)
                is_quota_error = 'quota' in error_str.lower() or '401' in error_str
                is_rate_limit = 'rate' in error_str.lower() or '429' in error_str

                # Log the error
                print(f"[WARN] TTS generation failed for {speaker}: {text[:50]}...")
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
        commentary_segments: list,
        show_progress: bool = True
    ) -> list[dict]:
        """
        Generate TTS audio for multiple commentary segments with speaker-specific voices.
        
        Args:
            commentary_segments: List of commentary dictionaries with 'commentary' and 'speaker' keys
            show_progress: Whether to print progress messages
        
        Returns:
            List of dictionaries with original commentary data plus 'audio_base64' field
        """
        results = []
        total = len(commentary_segments)
        
        for i, segment in enumerate(commentary_segments):
            if show_progress:
                speaker = segment.get('speaker', 'UNKNOWN')
                print(f"Generating TTS audio {i+1}/{total} ({speaker})...")
            
            text = segment['commentary']
            speaker = segment['speaker']
            
            # Generate audio with speaker-specific voice
            audio = self.generate_audio(text, speaker)
            
            # Add audio to segment
            segment_with_audio = segment.copy()
            segment_with_audio['audio_base64'] = audio
            results.append(segment_with_audio)
        
        return results
    
    def set_voice_for_speaker(self, speaker: str, voice_id: str) -> None:
        """
        Update the voice mapping for a specific speaker.
        
        Args:
            speaker: Speaker identifier (COMMENTATOR_1 or COMMENTATOR_2)
            voice_id: New voice ID to use for this speaker
        """
        if speaker not in ["COMMENTATOR_1", "COMMENTATOR_2"]:
            raise ValueError(f"Speaker must be COMMENTATOR_1 or COMMENTATOR_2, got: {speaker}")
        
        old_voice = self.voice_mapping.get(speaker, "None")
        self.voice_mapping[speaker] = voice_id
        print(f"[TTS] Updated {speaker} voice: {old_voice[:8]}... -> {voice_id[:8]}...")