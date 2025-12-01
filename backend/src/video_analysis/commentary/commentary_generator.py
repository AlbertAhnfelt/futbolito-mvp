"""
Commentary generation module.
Generates football commentary from detected events using Gemini API.
"""

import json
from pathlib import Path
from typing import Optional, List
from google import genai
from google.genai import types

from .models import Commentary, CommentaryOutput
from ..video.time_utils import parse_time_to_seconds, seconds_to_time, validate_commentary_duration
from ..context_manager import get_context_manager
from ..prompts import COMMENTARY_SYSTEM_PROMPT

# Try to import StateManager, but allow passing it in __init__ if import fails
try:
    from ..state_manager import StateManager
except ImportError:
    StateManager = None


class CommentaryGenerator:
    """
    Generates football commentary from detected events using Gemini API.

    Creates 5-30 second commentary segments with proper gaps and word limits.
    """

    def __init__(self, api_key: str, state_manager=None, output_dir: Optional[Path] = None):
        """
        Initialize commentary generator.

        Args:
            api_key: Gemini API key
            state_manager: StateManager instance for async-safe state updates (REQUIRED)
            output_dir: Directory to save commentary.json (default: output/)
        """
        self.client = genai.Client(api_key=api_key)
        self.context_manager = get_context_manager()

        # StateManager is the PRIMARY state management system
        self.state_manager = state_manager

        if self.state_manager is None:
            print("[COMMENTARY GENERATOR WARN] No StateManager provided. Commentary will work, but state won't be persisted properly.")

        # Output directory for backwards compatibility
        if output_dir is None:
            output_dir = Path("output")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.commentary_file = self.output_dir / 'commentary.json'

    def _build_prompt(self, events: list, video_duration: float) -> str:
        """
        Build the prompt for commentary generation.

        Args:
            events: List of event dictionaries
            video_duration: Total video duration in seconds

        Returns:
            Complete prompt string
        """
        prompt_parts = []

        # Add match context if available
        context_text = self.context_manager.format_for_prompt()
        if context_text:
            prompt_parts.append(context_text)
            prompt_parts.append("")

        # Add system prompt
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
        prompt_parts.append("1. Cover the important events from the match")
        prompt_parts.append("2. Are between 5-30 seconds each")
        prompt_parts.append("3. Have 1-4 second gaps between segments")
        prompt_parts.append("4. Stay within word limits (2.5 words/second MAX)")
        prompt_parts.append("5. Use player names when available from match context")
        prompt_parts.append("")
        prompt_parts.append("Return a JSON object with this structure:")
        prompt_parts.append("""{
  "commentaries": [
    {
      "start_time": "00:00:00",
      "end_time": "00:00:10",
      "commentary": "Text here (max 25 words for 10 seconds)"
    }
  ]
}""")

        return "\n".join(prompt_parts)

    async def generate_commentary(
        self,
        events: list,
        video_duration: float,
        use_streaming: bool = False
    ) -> List[Commentary]:
        """
        Generate commentary from detected events.
        ASYNC method that uses StateManager to persist state.

        Args:
            events: List of event dictionaries from events.json
            video_duration: Total video duration in seconds
            use_streaming: Whether to use streaming API (future enhancement)

        Returns:
            List of Commentary objects

        Raises:
            ValueError: If response is invalid
            RuntimeError: If API call fails
        """
        print(f"\n{'='*60}")
        print(f"COMMENTARY GENERATION STARTED")
        print(f"{'='*60}")
        print(f"Events to process: {len(events)}")
        print(f"Video duration: {seconds_to_time(video_duration)}")

        # Build prompt
        prompt = self._build_prompt(events, video_duration)

        try:
            # Generate content with JSON schema
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CommentaryOutput.model_json_schema()
                )
            )

            # Parse response
            response_text = response.text
            print(f"[COMMENTARY] Received response: {len(response_text)} characters")

            # Parse JSON and validate with Pydantic
            commentary_data = json.loads(response_text)
            commentary_output = CommentaryOutput(**commentary_data)

            print(f"[COMMENTARY] Generated {len(commentary_output.commentaries)} commentary segments")

            # Validate duration constraints
            commentaries_list = [c.model_dump() for c in commentary_output.commentaries]
            validated = validate_commentary_duration(commentaries_list)

            # Validate gaps between segments
            validated_commentaries = self._validate_gaps(validated)

            # Convert back to Commentary objects
            final_commentaries = [Commentary(**c) for c in validated_commentaries]

            # Save to StateManager (ASYNC)
            await self._save_commentaries(final_commentaries)

            print(f"\n{'='*60}")
            print(f"COMMENTARY GENERATION COMPLETED")
            print(f"{'='*60}")
            print(f"Total commentary segments: {len(final_commentaries)}")

            return final_commentaries

        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON response: {e}")
            print(f"[ERROR] Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")

        except Exception as e:
            print(f"[ERROR] Commentary generation failed: {e}")
            raise RuntimeError(f"Commentary generation API call failed: {e}")

    def _validate_gaps(self, commentaries: List[dict]) -> List[dict]:
        """
        Validate and enforce 1-4 second gaps between commentary segments.

        Args:
            commentaries: List of commentary dictionaries

        Returns:
            List of validated commentary dictionaries with proper gaps
        """
        MIN_GAP = 1  # seconds
        MAX_GAP = 2  # seconds

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
                print(f"[COMMENTARY] Adjusted start_time from {old_start} to {commentary['start_time']} (gap was {gap:.1f}s, min is {MIN_GAP}s)")

            # If gap is too large, warn but keep it (might be intentional for quiet periods)
            elif gap > MAX_GAP:
                print(f"[COMMENTARY] Warning: Large gap of {gap:.1f}s between segments (max recommended is {MAX_GAP}s)")

            # Check segment duration (5-30 seconds)
            start_secs = parse_time_to_seconds(commentary['start_time'])
            end_secs = parse_time_to_seconds(commentary['end_time'])
            duration = end_secs - start_secs

            if duration < 5:
                print(f"[COMMENTARY] Warning: Segment duration {duration:.1f}s is less than 5 seconds")
            elif duration > 30:
                # Trim to 30 seconds
                new_end = start_secs + 30
                old_end = commentary['end_time']
                commentary['end_time'] = seconds_to_time(new_end)
                print(f"[COMMENTARY] Trimmed end_time from {old_end} to {commentary['end_time']} (duration was {duration:.1f}s, max is 30s)")

            validated.append(commentary)

        return validated

    async def _save_commentaries(self, commentaries: List[Commentary]) -> None:
        """
        Save commentaries to StateManager (PRIMARY method).

        Args:
            commentaries: List of Commentary objects to save
        """
        if self.state_manager:
            try:
                # Convert Commentary objects to dicts
                commentary_dicts = [c.model_dump() for c in commentaries]
                # Save through StateManager (which handles file I/O)
                await self.state_manager.add_commentaries(commentary_dicts)
                print(f"[COMMENTARY] Saved {len(commentaries)} commentaries to StateManager")
            except Exception as e:
                print(f"[COMMENTARY ERROR] Failed to save commentaries to StateManager: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[COMMENTARY ERROR] No StateManager provided. Commentaries will NOT be saved!")
            print(f"[COMMENTARY ERROR] Lost {len(commentaries)} commentaries!")

    def load_commentaries(self) -> List[Commentary]:
        """
        Load commentaries from commentary.json file.

        Returns:
            List of Commentary objects

        Raises:
            FileNotFoundError: If commentary.json doesn't exist
        """
        if not self.commentary_file.exists():
            raise FileNotFoundError(f"Commentary file not found: {self.commentary_file}")

        with open(self.commentary_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        commentary_output = CommentaryOutput(**data)
        return commentary_output.commentaries

    def clear_commentaries(self) -> None:
        """Clear commentary.json file (reset to empty)."""
        if self.commentary_file.exists():
            self.commentary_file.unlink()
            print(f"[COMMENTARY] Cleared commentary file: {self.commentary_file}")
