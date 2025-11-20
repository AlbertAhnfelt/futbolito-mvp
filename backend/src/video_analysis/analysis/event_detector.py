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
from ..video.time_utils import seconds_to_time, parse_time_to_seconds
from ..video.video_splitter import VideoClip
from ..context_manager import get_context_manager
from ..prompts import EVENT_DETECTION_SYSTEM_PROMPT


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
        self.time_analyzed_file = self.output_dir / 'time_analyzed.txt'

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
        # Note: Gemini will return timestamps relative to the clip (starting at 00:00:00)
        # Our post-processing code adjusts these by adding interval_start offset
        start_time = seconds_to_time(interval_start)
        end_time = seconds_to_time(interval_end)
        prompt_parts.append(f"You are analyzing a {interval_end - interval_start}-second video clip.")
        prompt_parts.append(f"This clip represents the time range {start_time} to {end_time} of the original match.")
        prompt_parts.append("")
        prompt_parts.append("Analyze this video clip and return the events in JSON format with timestamps.")

        return "\n".join(prompt_parts)

    def _get_time_analyzed(self) -> int:
        """
        Get the current time_analyzed value.

        Returns:
            Number of seconds analyzed so far (0 if not started)
        """
        if not self.time_analyzed_file.exists():
            return 0

        try:
            with open(self.time_analyzed_file, 'r') as f:
                return int(f.read().strip())
        except (ValueError, IOError):
            return 0

    def _set_time_analyzed(self, seconds: int) -> None:
        """
        Update time_analyzed to the given value.

        CRITICAL: This should ONLY be called AFTER events.json has been written.
        This ensures downstream processes (like commentary generation) can safely
        read the new events before being triggered.

        Args:
            seconds: Number of seconds that have been analyzed
        """
        with open(self.time_analyzed_file, 'w') as f:
            f.write(str(seconds))
        print(f"[EVENT DETECTOR] Updated time_analyzed to {seconds}s")

    def detect_events_for_interval(
        self,
        file_uri: str,
        interval_start: int,
        interval_end: int
    ) -> List[Event]:
        """
        Detect events in a specific time interval of the video.

        Args:
            file_uri: Gemini file URI for the pre-split video clip
            interval_start: Start time in seconds (in the original video)
            interval_end: End time in seconds (in the original video)

        Returns:
            List of detected Event objects

        Raises:
            ValueError: If Gemini response is invalid
            RuntimeError: If API call fails
        """
        print(f"\n[EVENT DETECTOR] Analyzing interval {seconds_to_time(interval_start)} - {seconds_to_time(interval_end)}")

        # Build prompt with context
        prompt = self._build_prompt(interval_start, interval_end)

        # Create video part for pre-split clip
        video_part = types.Part(
            file_data=types.FileData(file_uri=file_uri)
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

            # Post-process timestamps: Add interval_start offset to all event times
            # When using pre-split clips, Gemini returns timestamps relative to the clip (0-30s)
            # We need to shift them to be relative to the full video
            for event in events_output.events:
                # Parse the event time to seconds
                event_seconds = parse_time_to_seconds(event.time)
                # Add the interval start offset
                corrected_seconds = event_seconds + interval_start
                # Convert back to time format
                event.time = seconds_to_time(corrected_seconds)

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

    def detect_events_from_clips(
        self,
        clips: List[VideoClip],
        clip_file_uris: List[str]
    ) -> List[Event]:
        """
        Detect all events from pre-split video clips.

        This method processes physically split video clips. Each clip is analyzed
        independently, and timestamps are automatically adjusted to match the full video.

        Args:
            clips: List of VideoClip objects with metadata
            clip_file_uris: List of Gemini file URIs (one per clip, in order)

        Returns:
            List of all detected events across all clips (sorted chronologically)

        Example:
            >>> detector = EventDetector(api_key="...")
            >>> splitter = VideoSplitter(ffmpeg_exe="...")
            >>> clips = splitter.split_video(video_path, duration=133, interval_seconds=30)
            >>> # Upload each clip to Gemini
            >>> clip_uris = []
            >>> for clip in clips:
            >>>     uploaded = client.files.upload(file=str(clip.path))
            >>>     clip_uris.append(uploaded.uri)
            >>> # Detect events
            >>> events = detector.detect_events_from_clips(clips, clip_uris)
        """
        if len(clips) != len(clip_file_uris):
            raise ValueError(f"Mismatch: {len(clips)} clips but {len(clip_file_uris)} URIs")

        print(f"\n{'='*60}")
        print(f"EVENT DETECTION STARTED")
        print(f"{'='*60}")
        print(f"Total clips to analyze: {len(clips)}")

        all_events = []

        # Analyze each clip
        for i, (clip, file_uri) in enumerate(zip(clips, clip_file_uris), 1):
            print(f"\n[{i}/{len(clips)}] Analyzing clip: {seconds_to_time(clip.start_time)} - {seconds_to_time(clip.end_time)}")
            print(f"[{i}/{len(clips)}] Clip file: {clip.path.name}")

            try:
                # Detect events for this clip
                events = self.detect_events_for_interval(
                    file_uri=file_uri,
                    interval_start=clip.start_time,
                    interval_end=clip.end_time
                )

                all_events.extend(events)

                # Save events to file after each clip
                # Sort before saving to ensure chronological order
                all_events.sort(key=lambda e: parse_time_to_seconds(e.time))
                self._save_events(all_events)

                print(f"[{i}/{len(clips)}] ✓ Completed. Total events so far: {len(all_events)}")

            except Exception as e:
                print(f"[{i}/{len(clips)}] ✗ Failed: {e}")
                # Continue with next clip even if this one fails
                continue

        # Final sort to ensure chronological order
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

    def detect_events_rolling_window(
        self,
        clips: List[VideoClip],
        clip_file_uris: List[str],
        video_duration: int
    ) -> List[Event]:
        """
        Detect events using the Producer rolling window workflow.

        This method implements the exact Producer logic flow:
        - Logic A: Process first 30 seconds (0-30s), write events.json, then update time_analyzed
        - Logic B: Loop through subsequent 30-second chunks with the same pattern

        CRITICAL: time_analyzed is ONLY updated AFTER events.json is written.
        This ensures downstream processes can safely read new events.

        Args:
            clips: List of VideoClip objects (pre-split, in order)
            clip_file_uris: List of Gemini file URIs (one per clip, in order)
            video_duration: Total duration of the video in seconds

        Returns:
            List of all detected events (sorted chronologically)
        """
        if len(clips) != len(clip_file_uris):
            raise ValueError(f"Mismatch: {len(clips)} clips but {len(clip_file_uris)} URIs")

        print(f"\n{'='*60}")
        print(f"PRODUCER ROLLING WINDOW - EVENT DETECTION STARTED")
        print(f"{'='*60}")
        print(f"Video duration: {video_duration}s")
        print(f"Total clips: {len(clips)}")
        print(f"Interval: 30 seconds per chunk")

        all_events = []

        # ============================================================
        # LOGIC A: Initialize with first 30 seconds (0-30s)
        # ============================================================
        if len(clips) == 0:
            print("[ERROR] No clips provided")
            return []

        first_clip = clips[0]
        first_uri = clip_file_uris[0]

        print(f"\n{'='*60}")
        print(f"LOGIC A: INITIALIZATION - First 30 seconds")
        print(f"{'='*60}")
        print(f"Processing interval: {seconds_to_time(first_clip.start_time)} - {seconds_to_time(first_clip.end_time)}")

        try:
            # 1. Analyze first 30 seconds
            events = self.detect_events_for_interval(
                file_uri=first_uri,
                interval_start=first_clip.start_time,
                interval_end=first_clip.end_time
            )
            all_events.extend(events)

            # 2. Write to events.json
            all_events.sort(key=lambda e: parse_time_to_seconds(e.time))
            self._save_events(all_events)
            print(f"[LOGIC A] Events written to {self.events_file}")

            # 3. CRITICAL: Update time_analyzed ONLY AFTER JSON is written
            self._set_time_analyzed(first_clip.end_time)
            print(f"[LOGIC A] ✓ Completed first 30 seconds. Total events: {len(all_events)}")

        except Exception as e:
            print(f"[LOGIC A] ✗ Failed to process first 30 seconds: {e}")
            raise

        # ============================================================
        # LOGIC B: Loop through remaining 30-second chunks
        # ============================================================
        if len(clips) > 1:
            print(f"\n{'='*60}")
            print(f"LOGIC B: ROLLING WINDOW LOOP - Remaining chunks")
            print(f"{'='*60}")
            print(f"Remaining clips to process: {len(clips) - 1}")

            for i in range(1, len(clips)):
                clip = clips[i]
                uri = clip_file_uris[i]

                print(f"\n[{i}/{len(clips)-1}] Processing interval: {seconds_to_time(clip.start_time)} - {seconds_to_time(clip.end_time)}")

                try:
                    # 1. Analyze next 30 seconds
                    events = self.detect_events_for_interval(
                        file_uri=uri,
                        interval_start=clip.start_time,
                        interval_end=clip.end_time
                    )
                    all_events.extend(events)

                    # 2. Write to events.json
                    all_events.sort(key=lambda e: parse_time_to_seconds(e.time))
                    self._save_events(all_events)
                    print(f"[LOGIC B] Events written to {self.events_file}")

                    # 3. CRITICAL: Update time_analyzed ONLY AFTER JSON is written
                    self._set_time_analyzed(clip.end_time)
                    print(f"[LOGIC B] [{i}/{len(clips)-1}] ✓ Completed. Total events: {len(all_events)}")

                except Exception as e:
                    print(f"[LOGIC B] [{i}/{len(clips)-1}] ✗ Failed: {e}")
                    # Continue with next chunk even if this one fails
                    continue

        # Final summary
        print(f"\n{'='*60}")
        print(f"PRODUCER ROLLING WINDOW - COMPLETED")
        print(f"{'='*60}")
        print(f"Total events detected: {len(all_events)}")
        print(f"Final time_analyzed: {self._get_time_analyzed()}s")
        print(f"Events saved to: {self.events_file}")
        print(f"Time tracking: {self.time_analyzed_file}")

        return all_events
