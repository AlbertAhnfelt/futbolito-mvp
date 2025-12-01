"""
Commentary generation module with dual commentator support.
Generates football commentary from detected events using Gemini API.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional, List
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

from .models import Commentary, CommentaryOutput
from ..video.time_utils import parse_time_to_seconds, seconds_to_time, validate_commentary_duration
from ..context_manager import get_context_manager
from ..prompts import COMMENTARY_SYSTEM_PROMPT, COMMENTARY_SYSTEM_PROMPT_1, COMMENTARY_SYSTEM_PROMPT_2, COMMENTARY_SYSTEM_CORE

# Try to import StateManager, but allow passing it in __init__ if import fails
try:
    from ..state_manager import StateManager
except ImportError:
    StateManager = None


class CommentaryGenerator:
    """
    Generates football commentary from detected events using Gemini API.
    
    Creates dual-commentator dialogue with proper speaker identification,
    timing, gaps, and word limits.
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
        Build the prompt for dual-commentator commentary generation.

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
    def _call_gemini_api_with_retry(self, prompt: str) -> str:
        """
        Call Gemini API with retry logic for quota exhaustion errors.

        Implements exponential backoff: 4s -> 8s -> 16s -> 32s -> 60s
        Max 5 attempts before giving up.

        Args:
            prompt: The prompt string to send to Gemini

        Returns:
            str: The response text from Gemini
        """
        print("[COMMENTARY] Calling Gemini API for dual-commentator generation...")
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CommentaryOutput.model_json_schema()
            )
        )
        return response.text

    def _sanitize_timestamps(self, commentary_data: dict) -> dict:
        """
        Sanitize timestamps by rounding fractional seconds to integers.

        Gemini sometimes returns timestamps like "00:00:42.5" despite the pattern constraint.
        This method normalizes them to "00:00:42" format.

        Args:
            commentary_data: Raw commentary data from Gemini

        Returns:
            dict: Commentary data with sanitized timestamps
        """
        def sanitize_time(time_str: str) -> str:
            """Convert HH:MM:SS.s to HH:MM:SS by rounding seconds."""
            # Match HH:MM:SS or HH:MM:SS.sss
            match = re.match(r'^(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$', time_str)
            if not match:
                return time_str  # Return as-is if format is unexpected

            hours, minutes, seconds, fractional = match.groups()

            # If no fractional part, return as-is
            if fractional is None:
                return time_str

            # Round the seconds (truncate fractional part for simplicity)
            total_seconds = int(seconds)

            # Return formatted timestamp
            return f"{hours}:{minutes}:{total_seconds:02d}"

        # Sanitize all commentary timestamps
        if 'commentaries' in commentary_data:
            for commentary in commentary_data['commentaries']:
                if 'start_time' in commentary:
                    original = commentary['start_time']
                    commentary['start_time'] = sanitize_time(original)
                    if original != commentary['start_time']:
                        print(f"[COMMENTARY] Sanitized start_time: {original} -> {commentary['start_time']}")

                if 'end_time' in commentary:
                    original = commentary['end_time']
                    commentary['end_time'] = sanitize_time(original)
                    if original != commentary['end_time']:
                        print(f"[COMMENTARY] Sanitized end_time: {original} -> {commentary['end_time']}")

        return commentary_data

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
            List of Commentary objects with speaker identification

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

    def _build_single_commentary_prompt(
        self,
        events: List[dict],
        events_covered: set,
        speaker: str,
        previous_commentaries: List[Commentary],
        previous_commentary_end: Optional[str],
        video_duration: float
    ) -> str:
        """
        Build prompt for generating a single commentary entry covering multiple events.
        Includes previous commentaries for natural conversational flow.

        Args:
            events: All events from the interval
            events_covered: Set of event times already covered by previous commentaries
            speaker: "COMMENTATOR_1" or "COMMENTATOR_2"
            previous_commentaries: List of all previous Commentary objects for context
            previous_commentary_end: End time of previous commentary (or None for first)
            video_duration: Total video duration in seconds

        Returns:
            Complete prompt string for single commentary
        """
        prompt_parts = []

        # Add match context if available
        context_text = self.context_manager.format_for_prompt()
        if context_text:
            prompt_parts.append(context_text)
            prompt_parts.append("")

        # Add role-specific system prompt
        if speaker == "COMMENTATOR_1":
            prompt_parts.append(COMMENTARY_SYSTEM_PROMPT_1)
        else:
            prompt_parts.append(COMMENTARY_SYSTEM_PROMPT_2)

        prompt_parts.append("")
        prompt_parts.append(COMMENTARY_SYSTEM_CORE)
        prompt_parts.append("")

        # Add previous commentaries for conversational context
        if previous_commentaries:
            prompt_parts.append("="*60)
            prompt_parts.append("PREVIOUS COMMENTARY (for conversational context):")
            prompt_parts.append("="*60)
            for prev in previous_commentaries:
                prompt_parts.append(f"[{prev.start_time} - {prev.end_time}] {prev.speaker}:")
                prompt_parts.append(f'  "{prev.commentary}"')
                prompt_parts.append("")
            prompt_parts.append("="*60)
            prompt_parts.append(f"You are now {speaker}. Respond naturally to continue the conversation.")
            prompt_parts.append("Build on what was said, react to previous comments, and maintain dialogue flow.")
            prompt_parts.append("="*60)
            prompt_parts.append("")

        # Filter out already covered events
        remaining_events = [e for e in events if e.get('time') not in events_covered]

        # Add event data
        prompt_parts.append("AVAILABLE EVENTS TO COMMENTATE:")
        prompt_parts.append(json.dumps({"events": remaining_events}, indent=2))
        prompt_parts.append("")

        if events_covered:
            prompt_parts.append(f"NOTE: {len(events_covered)} events have already been covered by previous commentaries.")
            prompt_parts.append("")

        # Add timing context
        prompt_parts.append(f"VIDEO DURATION: {seconds_to_time(video_duration)}")
        if previous_commentary_end:
            prompt_parts.append(f"PREVIOUS COMMENTARY ENDED AT: {previous_commentary_end}")
            prev_seconds = parse_time_to_seconds(previous_commentary_end)
            min_start = prev_seconds + 1.0  # Minimum 1s gap
            prompt_parts.append(f"YOUR COMMENTARY MUST START AT OR AFTER: {seconds_to_time(min_start)}")
        else:
            prompt_parts.append("This is the FIRST commentary of the match.")
        prompt_parts.append("")

        # Add specific instructions
        prompt_parts.append("Generate ONE commentary segment that:")
        prompt_parts.append(f"1. Is spoken by {speaker}")
        prompt_parts.append("2. Is 10-20 seconds long")
        prompt_parts.append("3. Has 1-2 second gap from previous commentary")
        prompt_parts.append("4. Stays within word limit (2.5 words/second MAX)")
        prompt_parts.append("5. Covers the EARLIEST uncovered events from the list above")
        prompt_parts.append("6. Can reference multiple events if they occur close together in time")
        prompt_parts.append("7. Focuses on the most significant events in your time window")
        if previous_commentaries:
            prompt_parts.append("8. RESPONDS NATURALLY to what was previously said in the conversation")
            prompt_parts.append("9. Maintains conversational flow and builds on previous comments")
        prompt_parts.append("")
        prompt_parts.append("CRITICAL: All timestamps MUST use integer seconds in HH:MM:SS format (e.g., 00:00:42, NOT 00:00:42.5)")
        prompt_parts.append("")
        prompt_parts.append("Return a JSON object with ONE commentary:")
        prompt_parts.append("""{
  "commentaries": [
    {
      "start_time": "HH:MM:SS",
      "end_time": "HH:MM:SS",
      "commentary": "Your commentary text here",
      "speaker": "%s"
    }
  ]
}""" % speaker)

        return "\n".join(prompt_parts)

    @retry(
        retry=retry_if_exception_type(ResourceExhausted),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    async def generate_single_commentary(
        self,
        events: List[dict],
        events_covered: set,
        speaker: str,
        previous_commentaries: List[Commentary],
        previous_commentary_end: Optional[str],
        video_duration: float
    ) -> tuple[Commentary, set]:
        """
        Generate a single 10-20 second commentary entry covering multiple events with one API call.
        Includes previous commentaries for natural conversational flow.

        Args:
            events: All events from the interval
            events_covered: Set of event times already covered
            speaker: "COMMENTATOR_1" or "COMMENTATOR_2"
            previous_commentaries: List of all previous Commentary objects for conversational context
            previous_commentary_end: End time of previous commentary (or None for first)
            video_duration: Total video duration in seconds

        Returns:
            Tuple of (Commentary object, Set of event times covered in this commentary)

        Raises:
            ValueError: If response is invalid
            RuntimeError: If API call fails
        """
        remaining = len([e for e in events if e.get('time') not in events_covered])
        print(f"[COMMENTARY] Generating single commentary as {speaker} ({remaining} events remaining, {len(previous_commentaries)} previous commentaries for context)")

        # Build prompt with conversational context
        prompt = self._build_single_commentary_prompt(
            events,
            events_covered,
            speaker,
            previous_commentaries,
            previous_commentary_end,
            video_duration
        )

        try:
            # Call API with retry logic
            response_text = await asyncio.to_thread(
                self._call_gemini_api_with_retry,
                prompt
            )

            # Parse JSON and sanitize timestamps
            commentary_data = json.loads(response_text)
            commentary_data = self._sanitize_timestamps(commentary_data)
            commentary_output = CommentaryOutput(**commentary_data)

            if not commentary_output.commentaries:
                raise ValueError("No commentary generated in response")

            # Return the single commentary
            commentary = commentary_output.commentaries[0]

            # Determine which events were covered by this commentary
            # Events within the commentary time window are considered covered
            commentary_start = parse_time_to_seconds(commentary.start_time)
            commentary_end = parse_time_to_seconds(commentary.end_time)

            newly_covered = set()
            for event in events:
                event_time = parse_time_to_seconds(event.get('time', '00:00:00'))
                # Mark event as covered if it falls within or near this commentary's timeframe
                if commentary_start - 2 <= event_time <= commentary_end + 2:
                    newly_covered.add(event.get('time'))

            print(f"[COMMENTARY] Generated: {commentary.start_time} - {commentary.end_time} ({speaker}), covered {len(newly_covered)} events")

            return commentary, newly_covered

        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON response: {e}")
            print(f"[ERROR] Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")

        except Exception as e:
            print(f"[ERROR] Single commentary generation failed: {e}")
            raise RuntimeError(f"Commentary generation API call failed: {e}")