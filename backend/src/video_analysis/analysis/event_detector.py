"""
Event detection module for video analysis.
Analyzes videos in 30-second intervals to detect football events.
"""

import json
import time
from pathlib import Path
from typing import Optional, List, Any
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

from .models import Event, EventsOutput
from ..video.time_utils import seconds_to_time, parse_time_to_seconds
from ..video.video_splitter import VideoClip
from ..context_manager import get_context_manager
from ..prompts import EVENT_DETECTION_SYSTEM_PROMPT
from ..utils.rate_limiter import gemini_rate_limiter

# Try to import StateManager, but allow passing it in __init__ if import fails
try:
    from ..state_manager import StateManager
except ImportError:
    StateManager = None

class EventDetector:
    """
    Detects football events from video using Gemini API.
    Uses StateManager to ensure thread-safe updates to events.json.
    """

    def __init__(self, api_key: str, state_manager=None, output_dir: Optional[Path] = None):
        self.client = genai.Client(api_key=api_key)
        self.context_manager = get_context_manager()

        # StateManager is the PRIMARY state management system
        self.state_manager = state_manager

        if self.state_manager is None:
            print("[EVENT DETECTOR WARN] No StateManager provided. Event detection will work, but state won't be persisted properly.")

        # Output directory for backwards compatibility (if no StateManager)
        if output_dir is None:
            output_dir = Path("output")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.events_file = self.output_dir / 'events.json'
        self.time_analyzed_file = self.output_dir / 'time_analyzed.txt'

    def _build_prompt(self, interval_start: int, interval_end: int) -> str:
        """Build the prompt for event detection."""
        prompt_parts = []

        # Add match context if available
        context_text = self.context_manager.format_for_prompt()
        if context_text:
            prompt_parts.append(context_text)
            prompt_parts.append("")

        # Add system prompt
        prompt_parts.append(EVENT_DETECTION_SYSTEM_PROMPT)
        prompt_parts.append("")

        # Add specific interval instructions
        duration = interval_end - interval_start
        prompt_parts.append(f"You are analyzing a {duration}-second video clip.")
        prompt_parts.append(f"Use timestamps 00:00:00 to {seconds_to_time(duration)}.")
        prompt_parts.append("Analyze this video clip and return the events in JSON format.")

        return "\n".join(prompt_parts)

    async def _update_state(self, new_events: List[Event], time_analyzed: int):
        """
        Centralized async method to update state through StateManager.
        This is the PRIMARY way to persist events.

        Args:
            new_events: List of Event objects detected
            time_analyzed: Time in seconds that has been analyzed
        """
        # 1. Convert Pydantic models to pure Python dicts for JSON serialization
        events_dicts = [event.model_dump() for event in new_events]

        # 2. Update via StateManager (PRIMARY method)
        if self.state_manager:
            try:
                # Add events to StateManager (which handles file I/O)
                await self.state_manager.add_events(events_dicts)
                # Update the time clock
                await self.state_manager.update_time_analyzed(time_analyzed)
                print(f"[EVENT DETECTOR] Successfully pushed {len(new_events)} events to StateManager.")
            except Exception as e:
                print(f"[EVENT DETECTOR ERROR] Failed to update StateManager: {e}")
                import traceback
                traceback.print_exc()
        else:
            # No StateManager - this should not happen in production
            print(f"[EVENT DETECTOR ERROR] No StateManager provided. Events will NOT be saved!")
            print(f"[EVENT DETECTOR ERROR] Lost {len(new_events)} events!")

    @retry(
        retry=retry_if_exception_type(ResourceExhausted),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _call_gemini_api_with_retry(self, content: types.Content) -> str:
        """
        Call Gemini API with retry logic for quota exhaustion errors.

        Implements exponential backoff: 4s -> 8s -> 16s -> 32s -> 60s
        Max 5 attempts before giving up.
        """
        # Enforce rate limiting before API call
        gemini_rate_limiter.wait_if_needed()

        print("[EVENT DETECTOR] Calling Gemini API...")
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=content,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EventsOutput.model_json_schema()
            )
        )
        return response.text

    def detect_events_for_interval(
        self,
        file_uri: str,
        interval_start: int,
        interval_end: int
    ) -> List[Event]:
        """
        Detect events in a specific time interval.
        Includes Sanity Clamping for timestamps.
        """
        clip_duration = interval_end - interval_start
        print(f"\n[EVENT DETECTOR] Analyzing interval {seconds_to_time(interval_start)} - {seconds_to_time(interval_end)} (Duration: {clip_duration}s)")

        prompt = self._build_prompt(interval_start, interval_end)

        video_part = types.Part(file_data=types.FileData(file_uri=file_uri))
        text_part = types.Part(text=prompt)
        content = types.Content(parts=[video_part, text_part])

        try:
            # Call API with retry logic and rate limiting
            response_text = self._call_gemini_api_with_retry(content)

            events_data = json.loads(response_text)
            events_output = EventsOutput(**events_data)

            print(f"[EVENT DETECTOR] Detected {len(events_output.events)} raw events")

            # --- IMPROVED TIMESTAMP VALIDATION AND CORRECTION ---
            valid_events = []
            TOLERANCE = 0.5  # Allow small overruns (e.g., 30.5s for 30s clip)

            for event in events_output.events:
                # 1. Parse raw time from model response
                raw_seconds = parse_time_to_seconds(event.time)
                original_time = event.time

                # 2. Check if timestamp is within acceptable range (with tolerance)
                if raw_seconds < (clip_duration + TOLERANCE):
                    # Valid or near-valid timestamp
                    if raw_seconds > clip_duration:
                        # Small overrun - clamp to clip duration
                        print(f"[TIMESTAMP FIX] Event time {original_time} slightly exceeds clip duration ({clip_duration}s). Adjusting to {clip_duration}s.")
                        raw_seconds = clip_duration

                    # Calculate absolute match time
                    absolute_seconds = interval_start + raw_seconds

                    # Final bounds check
                    if absolute_seconds > interval_end:
                        absolute_seconds = interval_end

                    # Update event with absolute timestamp
                    event.time = seconds_to_time(absolute_seconds)
                    valid_events.append(event)

                elif raw_seconds >= interval_start and raw_seconds < interval_end:
                    # Model gave absolute timestamp instead of relative!
                    corrected_seconds = raw_seconds - interval_start
                    print(f"[TIMESTAMP CORRECTION] Detected absolute timestamp {original_time} ({raw_seconds}s). Converting to relative: {seconds_to_time(corrected_seconds)} ({corrected_seconds}s)")

                    # Use the corrected relative timestamp
                    event.time = seconds_to_time(raw_seconds)  # Already absolute
                    valid_events.append(event)

                else:
                    # Truly invalid timestamp - discard event
                    print(f"[TIMESTAMP DISCARD] Event time {original_time} ({raw_seconds}s) is outside valid range (0-{clip_duration + TOLERANCE}s for clip, {interval_start}-{interval_end}s absolute). Skipping event: {event.description[:50]}...")
                    continue  # Skip this event

            # Summary
            discarded_count = len(events_output.events) - len(valid_events)
            if discarded_count > 0:
                print(f"[EVENT DETECTOR] Kept {len(valid_events)}/{len(events_output.events)} events ({discarded_count} discarded due to invalid timestamps)")
            else:
                print(f"[EVENT DETECTOR] All {len(valid_events)} events validated successfully")

            return valid_events

        except Exception as e:
            print(f"[ERROR] API call failed: {e}")
            raise

    async def detect_events_rolling_window(
        self,
        clips: List[VideoClip],
        clip_file_uris: List[str],
        video_duration: int
    ) -> List[Event]:
        """
        Producer Logic A -> B Flow.
        ASYNC method that uses StateManager to persist state.
        """
        if len(clips) != len(clip_file_uris):
            raise ValueError(f"Mismatch: Clips={len(clips)}, URIs={len(clip_file_uris)}")

        print(f"\n{'='*60}\nPRODUCER ROLLING WINDOW - STARTING\n{'='*60}")

        all_events_accumulator = []

        # LOGIC A: First Clip (Initialization)
        if len(clips) > 0:
            print(f"\n[LOGIC A] Processing initialization chunk (0-{clips[0].end_time}s)...")
            try:
                events = self.detect_events_for_interval(clip_file_uris[0], clips[0].start_time, clips[0].end_time)

                # Update accumulator for return value
                all_events_accumulator.extend(events)

                # PUSH UPDATE TO STATE MANAGER (ASYNC)
                await self._update_state(events, clips[0].end_time)

            except Exception as e:
                print(f"[LOGIC A] Fatal init error: {e}")
                raise

        # LOGIC B: Remaining Clips (Loop)
        if len(clips) > 1:
            print(f"\n[LOGIC B] Entering rolling loop for {len(clips)-1} remaining clips...")
            for i in range(1, len(clips)):
                try:
                    events = self.detect_events_for_interval(clip_file_uris[i], clips[i].start_time, clips[i].end_time)

                    # Update accumulator
                    all_events_accumulator.extend(events)

                    # PUSH UPDATE TO STATE MANAGER (ASYNC)
                    await self._update_state(events, clips[i].end_time)

                except Exception as e:
                    print(f"[LOGIC B] Chunk {i} failed, skipping: {e}")
                    continue

        print(f"\n[EVENT DETECTOR] Pipeline complete. Total events: {len(all_events_accumulator)}")
        return all_events_accumulator