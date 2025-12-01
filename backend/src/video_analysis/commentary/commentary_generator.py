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

from .models import Commentary
from ..video.time_utils import parse_time_to_seconds, seconds_to_time, validate_commentary_duration
from ..context_manager import get_context_manager
from ..prompts import (
    COMMENTARY_SYSTEM_PROMPT1,
    COMMENTARY_SYSTEM_PROMPT2,
    COMMENTARY_SYSTEM_CORE,
)

# Try to import StateManager, but allow passing it in __init__ if import fails
try:
    from ..state_manager import StateManager
except ImportError:
    StateManager = None


class CommentaryGenerator:
    """
    Generates football commentary from detected events using Gemini API.

    TRUE tiki-taka style:
    For each detected event, COMMENTATOR_1 (play-by-play) speaks first,
    then COMMENTATOR_2 (analyst) reacts to that line.
    """

    # Timing constraints (seconds)
    MIN_GAP = 0.5   # Minimum gap between segments (for natural dialogue)
    MAX_GAP = 2.0
    MIN_DURATION = 3
    MAX_DURATION = 15

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
        self.commentary_file = self.output_dir / "commentary.json"

    # =========================================================================
    # Low-level LLM call (single line generation)
    # =========================================================================

    @retry(
        retry=retry_if_exception_type(ResourceExhausted),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _call_gemini_line(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Gemini API once to generate a SINGLE commentary line (plain text).

        Args:
            system_prompt: System prompt for a specific commentator
            user_prompt: User prompt including event/context info

        Returns:
            str: Cleaned commentary line (no JSON, no extra quotes)
        """
        print("[COMMENTARY] Calling Gemini API for a single line...")
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="text/plain",
            ),
        )

        text = response.text.strip()

        # Simple cleaning for surrounding quotes
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()

        return text

    # =========================================================================
    # MAIN: events list → tiki-taka commentary
    # =========================================================================

    async def generate_commentary(
        self,
        events: list,
        video_duration: float,
        use_streaming: bool = False,
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
        """
        print(f"\n{'='*60}")
        print("TIKI-TAKA COMMENTARY GENERATION STARTED")
        print(f"{'='*60}")
        print(f"Events to process: {len(events)}")
        print(f"Video duration: {seconds_to_time(video_duration)}")
        print("Mode: Tiki-Taka (COMMENTATOR_1 → COMMENTATOR_2 per event)")

        context_text = self.context_manager.format_for_prompt()
        all_segments: List[dict] = []

        # Tracks the end time of the current commentary timeline (in seconds)
        time_cursor = 0.0

        for idx, event in enumerate(events):
            print(f"\n[COMMENTARY] Processing event {idx + 1}/{len(events)} @ {event.get('time')}")

            # Base time of the event
            event_time = parse_time_to_seconds(event["time"])

            # Determine COMMENTATOR_1 start time:
            # Either at the event time or after the previous segment plus MIN_GAP
            if not all_segments:
                c1_start = event_time
            else:
                last_end = parse_time_to_seconds(all_segments[-1]["end_time"])
                c1_start = max(event_time, last_end + self.MIN_GAP)

            # -----------------------------------------------------------------
            # 1) COMMENTATOR_1 (Play-by-play) line
            # -----------------------------------------------------------------
            c1_user_prompt = f"""
Match Context (if any):
{context_text}

Detected Event:
{json.dumps(event, indent=2)}

You are COMMENTATOR_1 (play-by-play).
Generate ONE natural commentary line for this moment.
- Focus on WHAT is happening right now.
- Use present tense.
- Use player names/numbers if available.
- Do NOT include timestamps or speaker labels.
- Output ONLY the spoken line, no JSON, no explanations.
"""

            c1_text = self._call_gemini_line(
                system_prompt=COMMENTARY_SYSTEM_PROMPT1 + COMMENTARY_SYSTEM_CORE,
                user_prompt=c1_user_prompt,
            )

            # Estimate speaking duration from word count (2.5 words/sec rule)
            c1_words = len(c1_text.split())
            est_c1_duration = max(self.MIN_DURATION, min(self.MAX_DURATION, c1_words / 2.5))
            c1_end = c1_start + est_c1_duration

            c1_segment = {
                "start_time": seconds_to_time(c1_start),
                "end_time": seconds_to_time(c1_end),
                "speaker": "COMMENTATOR_1",
                "commentary": c1_text,
            }
            all_segments.append(c1_segment)

            # -----------------------------------------------------------------
            # 2) COMMENTATOR_2 (Analyst) line — reacts to C1
            # -----------------------------------------------------------------
            c2_start = c1_end + self.MIN_GAP

            c2_user_prompt = f"""
Match Context (if any):
{context_text}

Detected Event:
{json.dumps(event, indent=2)}

COMMENTATOR_1 just said:
"{c1_text}"

You are COMMENTATOR_2 (analyst).
Generate ONE natural commentary line reacting to COMMENTATOR_1 and the event.
- Explain WHY/HOW, give tactical or technical insight.
- Do NOT repeat COMMENTATOR_1 literally.
- Do NOT include timestamps or speaker labels.
- Output ONLY the spoken line, no JSON, no explanations.
"""

            c2_text = self._call_gemini_line(
                system_prompt=COMMENTARY_SYSTEM_PROMPT2 + COMMENTARY_SYSTEM_CORE,
                user_prompt=c2_user_prompt,
            )

            c2_words = len(c2_text.split())
            est_c2_duration = max(self.MIN_DURATION, min(self.MAX_DURATION, c2_words / 2.5))
            c2_end = c2_start + est_c2_duration

            c2_segment = {
                "start_time": seconds_to_time(c2_start),
                "end_time": seconds_to_time(c2_end),
                "speaker": "COMMENTATOR_2",
                "commentary": c2_text,
            }
            all_segments.append(c2_segment)

            # Update timeline cursor
            time_cursor = c2_end

        # ---------------------------------------------------------------------
        # Validate durations and gaps (reuses existing validation logic)
        # ---------------------------------------------------------------------
        print(f"\n[COMMENTARY] Raw generated segments: {len(all_segments)}")

        validated = validate_commentary_duration(all_segments)
        validated_commentaries = self._validate_dual_commentary(validated)

        # Convert to Commentary objects
        final_commentaries = [Commentary(**c) for c in validated_commentaries]

        # Save to StateManager
        await self._save_commentaries(final_commentaries)

        # Logging
        print(f"\n{'='*60}")
        print("TIKI-TAKA COMMENTARY GENERATION COMPLETED")
        print(f"{'='*60}")
        print(f"Total commentary segments: {len(final_commentaries)}")

        final_speaker_counts = {}
        for c in final_commentaries:
            final_speaker_counts[c.speaker] = final_speaker_counts.get(c.speaker, 0) + 1
        print(f"Final speaker breakdown: {final_speaker_counts}")

        return final_commentaries

    # =========================================================================
    # Validation: gaps and timing (reuse logic with class-level constants)
    # =========================================================================

    def _validate_dual_commentary(self, commentaries: List[dict]) -> List[dict]:
        """
        Validate dual-commentator commentary with proper gaps and timing.

        Also validates that speakers alternate naturally.
        """
        MIN_GAP = self.MIN_GAP
        MAX_GAP = self.MAX_GAP
        MIN_DURATION = self.MIN_DURATION
        MAX_DURATION = self.MAX_DURATION

        validated = []

        for i, commentary in enumerate(commentaries):
            # First segment is always accepted
            if i == 0:
                validated.append(commentary)
                continue

            # Check gap from previous segment
            prev_end = parse_time_to_seconds(validated[-1]["end_time"])
            current_start = parse_time_to_seconds(commentary["start_time"])
            gap = current_start - prev_end

            # If gap is too small, adjust start_time
            if gap < MIN_GAP:
                new_start = prev_end + MIN_GAP
                old_start = commentary["start_time"]
                commentary["start_time"] = seconds_to_time(new_start)
                print(
                    f"[COMMENTARY] {commentary['speaker']}: Adjusted start_time "
                    f"from {old_start} to {commentary['start_time']} (gap was {gap:.1f}s)"
                )

            # If gap is too large, warn
            elif gap > MAX_GAP:
                print(
                    f"[COMMENTARY] Warning: Large gap of {gap:.1f}s between "
                    f"{validated[-1]['speaker']} and {commentary['speaker']}"
                )

            # Check segment duration
            start_secs = parse_time_to_seconds(commentary["start_time"])
            end_secs = parse_time_to_seconds(commentary["end_time"])
            duration = end_secs - start_secs

            if duration < MIN_DURATION:
                print(
                    f"[COMMENTARY] Warning: {commentary['speaker']} segment duration "
                    f"{duration:.1f}s is less than {MIN_DURATION}s"
                )
            elif duration > MAX_DURATION:
                # Trim to max duration
                new_end = start_secs + MAX_DURATION
                old_end = commentary["end_time"]
                commentary["end_time"] = seconds_to_time(new_end)
                print(
                    f"[COMMENTARY] {commentary['speaker']}: Trimmed end_time from "
                    f"{old_end} to {commentary['end_time']} (duration was {duration:.1f}s)"
                )

            # Check for speaker variety (warn if same speaker 3+ times in a row)
            if i >= 2:
                last_two_speakers = [validated[-2]["speaker"], validated[-1]["speaker"]]
                if all(s == commentary["speaker"] for s in last_two_speakers):
                    print(f"[COMMENTARY] Note: {commentary['speaker']} speaking 3 times in a row")

            validated.append(commentary)

        return validated

    # =========================================================================
    # StateManager save
    # =========================================================================

    async def _save_commentaries(self, commentaries: List[Commentary]) -> None:
        """
        Save commentaries to StateManager (PRIMARY method).
        """
        if self.state_manager:
            try:
                commentary_dicts = [c.model_dump() for c in commentaries]
                await self.state_manager.add_commentaries(commentary_dicts)
                print(f"[COMMENTARY] Saved {len(commentaries)} commentaries to StateManager")
            except Exception as e:
                print(f"[COMMENTARY ERROR] Failed to save commentaries to StateManager: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[COMMENTARY ERROR] No StateManager provided. Commentaries will NOT be saved!")
            print(f"[COMMENTARY ERROR] Lost {len(commentaries)} commentaries!")

    # =========================================================================
    # File-based load / clear (for backwards compatibility)
    # =========================================================================

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

        with open(self.commentary_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Assumes the file format is {"commentaries": [...]}
        return [Commentary(**c) for c in data.get("commentaries", [])]

    def clear_commentaries(self) -> None:
        """Clear commentary.json file (reset to empty)."""
        if self.commentary_file.exists():
            self.commentary_file.unlink()
            print(f"[COMMENTARY] Cleared commentary file: {self.commentary_file}")
