"""
Text-to-speech generation using ElevenLabs API.

This module handles conversion of text commentary to audio.
"""

import base64
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
        model_id: str = "eleven_multilingual_v2"
    ) -> str:
        """
        Generate TTS audio and return as base64 string.
        
        Args:
            text: The text to convert to speech
            voice_id: The ElevenLabs voice ID to use (uses default if None)
            model_id: The model to use for generation
        
        Returns:
            Base64 encoded audio data (empty string on error)
        """
        try:
            voice = voice_id or self.default_voice_id
            
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
            print(f"⚠️  TTS generation failed for text: {text[:50]}...")
            print(f"   Error: {str(e)}")
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

