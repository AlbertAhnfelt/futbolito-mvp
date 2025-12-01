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

    # ==========================================
    # CALL GEMINI WITH RETRY
    # ==========================================

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

            c1_text = self._call_llm(
                system_prompt=COMMENTARY_SYSTEM_PROMPT1 + COMMENTARY_SYSTEM_CORE,
                user_prompt=c1_user_prompt
            )

            # estimate duration
            c1_duration = min(max(len(c1_text.split()) / 2.5, self.MIN_DURATION), self.MAX_DURATION)
            c1_end = event_time + c1_duration

            segment_c1 = {
                "start_time": seconds_to_time(event_time),
                "end_time": seconds_to_time(c1_end),
                "speaker": "COMMENTATOR_1",
                "text": c1_text,
            }
            final_segments.append(segment_c1)

            # -------------------------------------------------
            # 2) Generate COMMENTATOR_2 reaction
            # -------------------------------------------------

            c2_start = c1_end + self.MIN_GAP

            c2_user_prompt = f"""
Match Context:
{context_text}

Event:
{json.dumps(event, indent=2)}

COMMENTATOR_1 just said:
\"{c1_text}\"

Generate ONE commentary segment reacting naturally as COMMENTATOR_2.
Start time MUST be:
{seconds_to_time(c2_start)}
"""

            c2_text = self._call_llm(
                system_prompt=COMMENTARY_SYSTEM_PROMPT2 + COMMENTARY_SYSTEM_CORE,
                user_prompt=c2_user_prompt
            )

            c2_duration = min(max(len(c2_text.split()) / 2.5, self.MIN_DURATION), self.MAX_DURATION)
            c2_end = c2_start + c2_duration

            segment_c2 = {
                "start_time": seconds_to_time(c2_start),
                "end_time": seconds_to_time(c2_end),
                "speaker": "COMMENTATOR_2",
                "text": c2_text,
            }
            final_segments.append(segment_c2)

        # -------------------------------------------------
        # Save to StateManager
        # -------------------------------------------------

        await self._save_commentaries(final_segments)

        print("============================================")
        print("TIKI-TAKA COMMENTARY GENERATION COMPLETE")
        print("============================================")

        return [Commentary(**c) for c in final_segments]

    # ==========================================
    # SAVE
    # ==========================================

    async def _save_commentaries(self, commentaries: List[dict]):
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
