"""
Event detection module for video analysis.
Analyzes videos in 30-second intervals to detect football events.
"""

import json
from pathlib import Path
from typing import Optional, List
from google import genai
from google.genai import types

from .models import Event, EventsOutput
from ..video.time_utils import calculate_video_intervals, seconds_to_time, parse_time_to_seconds
from ..context_manager import get_context_manager


# System prompt for event detection (from plan/system_prompt.md)
EVENT_DETECTION_SYSTEM_PROMPT = """You are an AI video analyzer that detects and catalogs football gameplay events from a given video clip.
Your goal is to return a single JSON object named events.json that contains all detected events in chronological order.

RULES:

Visual-only analysis:
Use only the visual information in the video (player movements, ball, referee signals, on-screen text, replays, etc).
Ignore all audio or commentary.

Event detection:
Identify all meaningful gameplay moments, such as:

Passes, dribbles, tackles, fouls, saves, shots, goals, throw-ins, corners, free kicks, offsides, etc.

Replays or slow-motion sequences.

Periods of high/low intensity or transitions (e.g., counterattacks).

CRITICAL - MAXIMUM DETAIL REQUIRED:
Your descriptions MUST be extremely detailed and specific. Follow these rules:

1. PLAYER IDENTIFICATION:
   - ALWAYS identify players by their jersey number AND name if visible on screen, jerseys, or overlays
   - If a name appears on screen (e.g., "Zlatan Ibrahimović"), use it in your description
   - Never use vague terms like "player in yellow jersey" - always specify the player identifier
   - Format: "Player #10 Messi" or "Zlatan Ibrahimović" or "Player #7"

2. SPECIFIC ACTIONS:
   - Be extremely precise about the TYPE of action performed
   - For goals/shots: Specify exact technique (e.g., "bicycle kick", "volley", "header", "chip", "curled shot", "low drive")
   - For passes: Specify type (e.g., "through ball", "cross", "back pass", "one-two")
   - For dribbles: Describe moves (e.g., "stepover", "nutmeg", "body feint", "elastico")
   - For tackles: Specify type (e.g., "sliding tackle", "standing tackle", "interception")

3. POSITIONING AND MOVEMENT:
   - Include WHERE on the field the action occurs (e.g., "from 30 yards out", "inside the penalty box", "from the left wing")
   - Describe trajectory of the ball (e.g., "ball arcs over the goalkeeper", "low shot to bottom corner")

4. CONTEXT:
   - Include relevant defenders, goalkeeper actions, or team dynamics
   - Mention the score overlay if visible
   - Note any special circumstances (e.g., "under pressure from two defenders")

Example of GOOD description:
"Zlatan Ibrahimović (#10) performs an acrobatic bicycle kick from 25 yards out, sending the ball arcing over England goalkeeper Joe Hart into the top corner of the net. Sweden vs England, Ibrahimović falling backwards as he executes the overhead kick."

Example of BAD description (too vague):
"Player in yellow jersey kicks the ball over the goalie, making the goal."

Output format:
Return one JSON object with the key "events", containing an array of event objects.
Each event object must exactly follow this structure:

{
  "time": "HH:MM:SS",
  "description": "EXTREMELY DETAILED technical description with specific player names, exact action types, field positions, and ball trajectory.",
  "players": [
    "Zlatan Ibrahimović #10",
    "#7",
    "Joe Hart"
  ],
  "replay": false,
  "intensity": 5
}


Notes:

"time" → timecode in the video when the event starts (HH:MM:SS).

"players" → Include ALL visible player identifiers with names if shown on screen (jersey numbers, names from overlays, graphics, etc).

"replay" → boolean: true if it's a replay segment, false if live action.

"intensity" → integer from 1 (calm) to 10 (very intense).

"description" → MUST be highly detailed with specific technique names, player identifications, positions, and trajectories. Minimum 15 words for significant events.

Formatting:

Return only valid JSON.

Do not include any extra explanations, markdown, or comments.

Do not include trailing commas."""


class EventDetector:
    """
    Detects football events from video using Gemini API.

    Analyzes videos in 30-second intervals and extracts events with
    timestamps, descriptions, player involvement, and intensity ratings.
    """

    def __init__(self, api_key: str, output_dir: Optional[Path] = None):
        """
        Initialize event detector.

        Args:
            api_key: Gemini API key
            output_dir: Directory to save events.json (default: project_root/output/)
        """
        self.client = genai.Client(api_key=api_key)
        self.context_manager = get_context_manager()

        if output_dir is None:
            # Default to project_root/output/
            output_dir = Path(__file__).parent.parent.parent.parent.parent / 'output'

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.events_file = self.output_dir / 'events.json'

    def _build_prompt(self, interval_start: int, interval_end: int) -> str:
        """
        Build the prompt for event detection, optionally including match context.

        Args:
            interval_start: Start time in seconds
            interval_end: End time in seconds

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
        prompt_parts.append(EVENT_DETECTION_SYSTEM_PROMPT)
        prompt_parts.append("")

        # Add interval information
        start_time = seconds_to_time(interval_start)
        end_time = seconds_to_time(interval_end)
        prompt_parts.append(f"IMPORTANT: You are analyzing a {interval_end - interval_start}-second segment from {start_time} to {end_time}.")
        prompt_parts.append(f"All event timestamps should be relative to the FULL VIDEO, not this segment.")
        prompt_parts.append(f"For example, if you see an event at 0:05 in this segment, and this segment starts at {start_time}, record the time as {start_time} + 0:05.")
        prompt_parts.append("")
        prompt_parts.append("Analyze this video segment and return the events in JSON format.")

        return "\n".join(prompt_parts)

    def detect_events_for_interval(
        self,
        file_uri: str,
        interval_start: int,
        interval_end: int
    ) -> List[Event]:
        """
        Detect events in a specific time interval of the video.

        Args:
            file_uri: Gemini file URI for the uploaded video
            interval_start: Start time in seconds
            interval_end: End time in seconds

        Returns:
            List of detected Event objects

        Raises:
            ValueError: If Gemini response is invalid
            RuntimeError: If API call fails
        """
        print(f"\n[EVENT DETECTOR] Analyzing interval {seconds_to_time(interval_start)} - {seconds_to_time(interval_end)}")

        # Build prompt with context
        prompt = self._build_prompt(interval_start, interval_end)

        # Create video part with metadata (correct syntax per Gemini API docs)
        video_part = types.Part(
            file_data=types.FileData(file_uri=file_uri),
            video_metadata=types.VideoMetadata(
                start_offset=f"{interval_start}s",
                end_offset=f"{interval_end}s"
            )
        )

        # Create text part for prompt
        text_part = types.Part(text=prompt)

        # Create content with both parts
        content = types.Content(parts=[video_part, text_part])

        try:
            # Generate content with JSON schema
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=content,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=EventsOutput.model_json_schema()
                )
            )

            # Parse response
            response_text = response.text
            print(f"[EVENT DETECTOR] Received response: {len(response_text)} characters")

            # DEBUG: Print raw response to see what Gemini returned
            print(f"[EVENT DETECTOR] Raw JSON response:")
            print(response_text)
            print("[EVENT DETECTOR] ---")

            # Parse JSON and validate with Pydantic
            events_data = json.loads(response_text)
            events_output = EventsOutput(**events_data)

            print(f"[EVENT DETECTOR] Detected {len(events_output.events)} events in this interval")

            # Log detected event times for debugging
            if events_output.events:
                for event in events_output.events:
                    print(f"[EVENT DETECTOR]   Event at {event.time}: {event.description[:60]}...")
            else:
                print(f"[EVENT DETECTOR]   No events detected in this interval")

            return events_output.events

        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON response: {e}")
            print(f"[ERROR] Response text: {response_text}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")

        except Exception as e:
            print(f"[ERROR] Event detection failed: {e}")
            raise RuntimeError(f"Event detection API call failed: {e}")

    def detect_events(
        self,
        file_uri: str,
        duration_seconds: float,
        interval_seconds: int = 30
    ) -> List[Event]:
        """
        Detect all events in a video by analyzing 30-second intervals.

        Args:
            file_uri: Gemini file URI for the uploaded video
            duration_seconds: Total video duration in seconds
            interval_seconds: Length of each analysis interval (default: 30)

        Returns:
            List of all detected events across the entire video

        Example:
            >>> detector = EventDetector(api_key="...")
            >>> events = detector.detect_events(file_uri="...", duration_seconds=133)
            >>> print(f"Detected {len(events)} events")
        """
        print(f"\n{'='*60}")
        print(f"EVENT DETECTION STARTED")
        print(f"{'='*60}")
        print(f"Video duration: {seconds_to_time(duration_seconds)} ({duration_seconds}s)")
        print(f"Interval length: {interval_seconds}s")

        # Calculate intervals
        intervals = calculate_video_intervals(duration_seconds, interval_seconds)
        print(f"Total intervals to analyze: {len(intervals)}")

        all_events = []

        # Analyze each interval
        for i, (start, end) in enumerate(intervals, 1):
            print(f"\n[{i}/{len(intervals)}] Analyzing interval: {seconds_to_time(start)} - {seconds_to_time(end)}")

            try:
                events = self.detect_events_for_interval(file_uri, int(start), int(end))
                all_events.extend(events)

                # Save events to file after each interval
                self._save_events(all_events)

                print(f"[{i}/{len(intervals)}] ✓ Completed. Total events so far: {len(all_events)}")

            except Exception as e:
                print(f"[{i}/{len(intervals)}] ✗ Failed: {e}")
                # Continue with next interval even if this one fails
                continue

        # Sort events chronologically by time before final save
        all_events.sort(key=lambda e: parse_time_to_seconds(e.time))

        # Save sorted events
        self._save_events(all_events)

        print(f"\n{'='*60}")
        print(f"EVENT DETECTION COMPLETED")
        print(f"{'='*60}")
        print(f"Total events detected: {len(all_events)}")
        print(f"Events saved to: {self.events_file} (sorted chronologically)")

        return all_events

    def _save_events(self, events: List[Event]) -> None:
        """
        Save events to events.json file.

        Args:
            events: List of Event objects to save
        """
        events_output = EventsOutput(events=events)

        with open(self.events_file, 'w', encoding='utf-8') as f:
            json.dump(
                events_output.model_dump(),
                f,
                indent=2,
                ensure_ascii=False
            )

        print(f"[EVENT DETECTOR] Saved {len(events)} events to {self.events_file}")

    def load_events(self) -> List[Event]:
        """
        Load events from events.json file.

        Returns:
            List of Event objects

        Raises:
            FileNotFoundError: If events.json doesn't exist
        """
        if not self.events_file.exists():
            raise FileNotFoundError(f"Events file not found: {self.events_file}")

        with open(self.events_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        events_output = EventsOutput(**data)
        return events_output.events

    def clear_events(self) -> None:
        """Clear events.json file (reset to empty)."""
        if self.events_file.exists():
            self.events_file.unlink()
            print(f"[EVENT DETECTOR] Cleared events file: {self.events_file}")
