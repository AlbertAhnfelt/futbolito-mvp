"""
Commentary generation module with dual commentator support.
Generates football commentary from detected events using Gemini API.
"""

import json
from pathlib import Path
from typing import Optional, List
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

from .models import Commentary, CommentaryOutput
from ..video.time_utils import parse_time_to_seconds, seconds_to_time
from ..context_manager import get_context_manager
from ..prompts import (
    COMMENTARY_SYSTEM_PROMPT1,
    COMMENTARY_SYSTEM_PROMPT2,
    COMMENTARY_SYSTEM_CORE,
)
from ..utils.rate_limiter import gemini_rate_limiter

try:
    from ..state_manager import StateManager
except ImportError:
    StateManager = None


class CommentaryGenerator:
    """
    Generates football commentary using TRUE tiki-taka style:
    COMMENTATOR_1 (play-by-play) → COMMENTATOR_2 (analysis) for each event.
    """

    MIN_GAP = 0.5
    MAX_GAP = 2.0
    MIN_DURATION = 3
    MAX_DURATION = 15

    def __init__(self, api_key: str, state_manager=None, output_dir: Optional[Path] = None):
        self.client = genai.Client(api_key=api_key)
        self.context_manager = get_context_manager()
        self.state_manager = state_manager

        if output_dir is None:
            output_dir = Path("output")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.commentary_file = self.output_dir / "commentary.json"

        # Add match context if available
        context_text = self.context_manager.format_for_prompt()
        if context_text:
            prompt_parts.append(context_text)
            prompt_parts.append("")

        # Add system prompt (now with dual commentator instructions)
        prompt_parts.append(COMMENTARY_SYSTEM_PROMPT)
        prompt_parts.append("")

        # Add events data
        prompt_parts.append("DETECTED EVENTS:")
        prompt_parts.append(json.dumps({"events": events}, indent=2))
        prompt_parts.append("")

        # Add specific instructions
        prompt_parts.append(f"VIDEO DURATION: {seconds_to_time(video_duration)}")
        prompt_parts.append("")
        prompt_parts.append("Generate commentary segments that:")
        prompt_parts.append("1. Create natural dialogue between COMMENTATOR_1 and COMMENTATOR_2")
        prompt_parts.append("2. Each segment is 10-20 seconds")
        prompt_parts.append("3. Have 0.5-2 second gaps between segments")
        prompt_parts.append("4. Stay within word limits (2.5 words/second MAX)")
        prompt_parts.append("5. Alternate speakers naturally - respond to each other")
        prompt_parts.append("6. Use player names from match context when available")
        prompt_parts.append("7. COMMENTATOR_1 leads play-by-play, COMMENTATOR_2 adds analysis/excitement")
        prompt_parts.append("")
        prompt_parts.append("CRITICAL: All timestamps MUST use integer seconds in HH:MM:SS format (e.g., 00:00:42, NOT 00:00:42.5)")
        prompt_parts.append("")
        prompt_parts.append("Return a JSON object with this structure:")
        prompt_parts.append("""{
  "commentaries": [
    {
      "start_time": "00:00:00",
      "end_time": "00:00:05",
      "commentary": "Text here (max 12 words for 5 seconds)",
      "speaker": "COMMENTATOR_1"
    },
    {
      "start_time": "00:00:06",
      "end_time": "00:00:10",
      "commentary": "Response text (max 10 words for 4 seconds)",
      "speaker": "COMMENTATOR_2"
    }
  ]
}""")

        return "\n".join(prompt_parts)

    @retry(
        retry=retry_if_exception_type(ResourceExhausted),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call Gemini for one commentator's line."""
        gemini_rate_limiter.wait_if_needed()

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="text/plain"
            )
        )
        return response.text.strip()

    # ==========================================
    # TIKI-TAKA COMMENTARY GENERATION
    # ==========================================

    async def generate_commentary(
        self,
        events: list,
        video_duration: float,
        use_streaming: bool = False
    ) -> List[Commentary]:

        print("\n============================================")
        print("TIKI-TAKA COMMENTARY GENERATION STARTED")
        print("============================================")

        time_cursor = 0.0
        final_segments = []

        context_text = self.context_manager.format_for_prompt()

        for event in events:
            event_time = parse_time_to_seconds(event["time"])
            intensity = event.get("intensity", 5)

            # Ensure minimum gap
            if final_segments:
                last_end = parse_time_to_seconds(final_segments[-1]["end_time"])
                gap = event_time - last_end
                if gap < self.MIN_GAP:
                    event_time = last_end + self.MIN_GAP

            # -------------------------------------------------
            # 1) Generate COMMENTATOR_1 line
            # -------------------------------------------------

            c1_user_prompt = f"""
Match Context:
{context_text}

Event:
{json.dumps(event, indent=2)}

Generate ONE commentary segment for COMMENTATOR_1.
It must be {self.MIN_DURATION}-{self.MAX_DURATION} seconds long.
Start time MUST be based on:
{seconds_to_time(event_time)}
"""

    async def generate_commentary(
        self,
        events: list,
        video_duration: float,
        use_streaming: bool = False
    ) -> List[Commentary]:
        """
        Generate dual-commentator commentary from detected events.
        ASYNC method that uses StateManager to persist state.

        Args:
            events: List of event dictionaries from events.json
            video_duration: Total video duration in seconds
            use_streaming: Whether to use streaming API (future enhancement)

        Returns:
            List of Commentary objects with speaker identification

        Raises:
            ValueError: If response is invalid
            RuntimeError: If API call fails
        """
        print(f"\n{'='*60}")
        print(f"DUAL COMMENTARY GENERATION STARTED")
        print(f"{'='*60}")
        print(f"Events to process: {len(events)}")
        print(f"Video duration: {seconds_to_time(video_duration)}")
        print(f"Mode: Dual Commentator (COMMENTATOR_1 + COMMENTATOR_2)")

        # Build prompt
        prompt = self._build_prompt(events, video_duration)

        try:
            # Call API with retry logic and rate limiting
            response_text = self._call_gemini_api_with_retry(prompt)
            print(f"[COMMENTARY] Received response: {len(response_text)} characters")

            # Parse JSON and sanitize timestamps (Gemini sometimes returns decimals)
            commentary_data = json.loads(response_text)
            commentary_data = self._sanitize_timestamps(commentary_data)
            commentary_output = CommentaryOutput(**commentary_data)

            print(f"[COMMENTARY] Generated {len(commentary_output.commentaries)} commentary segments")
            
            # Count segments per speaker
            speaker_counts = {}
            for c in commentary_output.commentaries:
                speaker_counts[c.speaker] = speaker_counts.get(c.speaker, 0) + 1
            print(f"[COMMENTARY] Speaker breakdown: {speaker_counts}")

            # Validate duration constraints
            commentaries_list = [c.model_dump() for c in commentary_output.commentaries]
            validated = validate_commentary_duration(commentaries_list)

            # Validate gaps and timing
            validated_commentaries = self._validate_dual_commentary(validated)

            # Convert back to Commentary objects
            final_commentaries = [Commentary(**c) for c in validated_commentaries]

            # Save to StateManager (ASYNC)
            await self._save_commentaries(final_commentaries)

            print(f"\n{'='*60}")
            print(f"DUAL COMMENTARY GENERATION COMPLETED")
            print(f"{'='*60}")
            print(f"Total commentary segments: {len(final_commentaries)}")
            
            # Final speaker counts
            final_speaker_counts = {}
            for c in final_commentaries:
                final_speaker_counts[c.speaker] = final_speaker_counts.get(c.speaker, 0) + 1
            print(f"Final speaker breakdown: {final_speaker_counts}")

            return final_commentaries

        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON response: {e}")
            print(f"[ERROR] Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")

        except Exception as e:
            print(f"[ERROR] Commentary generation failed: {e}")
            raise RuntimeError(f"Commentary generation API call failed: {e}")

    def _validate_dual_commentary(self, commentaries: List[dict]) -> List[dict]:
        """
        Validate dual-commentator commentary with proper gaps and timing.
        
        Also validates that speakers alternate naturally.

        Args:
            commentaries: List of commentary dictionaries with speaker field

        Returns:
            List of validated commentary dictionaries
        """
        MIN_GAP = 0.5  # seconds (shorter for natural dialogue)
        MAX_GAP = 2.0  # seconds
        MIN_DURATION = 10  # seconds
        MAX_DURATION = 20  # seconds

        validated = []

        for i, commentary in enumerate(commentaries):
            # First segment is always OK
            if i == 0:
                validated.append(commentary)
                continue

            # Check gap from previous segment
            prev_end = parse_time_to_seconds(validated[-1]['end_time'])
            current_start = parse_time_to_seconds(commentary['start_time'])
            gap = current_start - prev_end

            # If gap is too small, adjust start_time
            if gap < MIN_GAP:
                new_start = prev_end + MIN_GAP
                old_start = commentary['start_time']
                commentary['start_time'] = seconds_to_time(new_start)
                print(f"[COMMENTARY] {commentary['speaker']}: Adjusted start_time from {old_start} to {commentary['start_time']} (gap was {gap:.1f}s)")

            # If gap is too large, warn
            elif gap > MAX_GAP:
                print(f"[COMMENTARY] Warning: Large gap of {gap:.1f}s between {validated[-1]['speaker']} and {commentary['speaker']}")

            # Check segment duration
            start_secs = parse_time_to_seconds(commentary['start_time'])
            end_secs = parse_time_to_seconds(commentary['end_time'])
            duration = end_secs - start_secs

            if duration < MIN_DURATION:
                print(f"[COMMENTARY] Warning: {commentary['speaker']} segment duration {duration:.1f}s is less than {MIN_DURATION}s")
            elif duration > MAX_DURATION:
                # Trim to max duration
                new_end = start_secs + MAX_DURATION
                old_end = commentary['end_time']
                commentary['end_time'] = seconds_to_time(new_end)
                print(f"[COMMENTARY] {commentary['speaker']}: Trimmed end_time from {old_end} to {commentary['end_time']} (duration was {duration:.1f}s)")

            # Check for speaker variety (warn if same speaker 3+ times in a row)
            if i >= 2:
                last_two_speakers = [validated[-2]['speaker'], validated[-1]['speaker']]
                if all(s == commentary['speaker'] for s in last_two_speakers):
                    print(f"[COMMENTARY] Note: {commentary['speaker']} speaking 3 times in a row")

            validated.append(commentary)

        return validated

    async def _save_commentaries(self, commentaries: List[Commentary]) -> None:
        """
        Save commentaries to StateManager (PRIMARY method).

        Args:
            commentaries: List of Commentary objects to save
        """
        if self.state_manager:
            await self.state_manager.add_commentaries(commentaries)
            print(f"[COMMENTARY] Saved {len(commentaries)} commentary segments.")
        else:
            print("[COMMENTARY WARNING] No StateManager provided.")

    # ==========================================
    # LOAD & CLEAR
    # ==========================================

    def load_commentaries(self) -> List[Commentary]:
        if not self.commentary_file.exists():
            raise FileNotFoundError(f"Commentary file not found: {self.commentary_file}")

        with open(self.commentary_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        commentary_output = CommentaryOutput(**data)
        return commentary_output.commentaries

    def clear_commentaries(self) -> None:
        if self.commentary_file.exists():
            self.commentary_file.unlink()
            print(f"[COMMENTARY] Cleared commentary file: {self.commentary_file}")
