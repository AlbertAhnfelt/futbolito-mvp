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
from .graph_nodes import SlowPlayNode, FastPlayNode, CommentaryNode


# System prompt for commentary generation
COMMENTARY_SYSTEM_PROMPT = """You are a professional football commentator generating exciting and engaging commentary for a football match.

Your task is to create commentary segments based on detected events from the match. Each commentary segment should:

1. Duration: Be between 5-30 seconds long
2. Gaps: Have a 1-4 second gap between segments (between previous end_time and this start_time)
3. Word count: Stay within the word limit (max 2.5 words per second)
   - Example: A 10-second segment should have MAX 25 words
4. Style: Be engaging, descriptive, and match the intensity of the events
5. Coverage: Cover multiple related events in a single segment when appropriate

IMPORTANT RULES:
- Do NOT overlap commentary segments
- Ensure gaps of 1-4 seconds between consecutive segments
- Respect the word count limit strictly (2.5 words/second MAX)
- Use player names when available (from match context)
- Match the tone to the intensity of events (calm for low intensity, excited for high intensity)
- Create natural, flowing commentary that tells the story of the match

Return a JSON object with a "commentaries" array containing commentary segments."""


class CommentaryGenerator:
    """
    Generates football commentary from detected events using Gemini API.

    Creates 5-30 second commentary segments with proper gaps and word limits.
    """

    def __init__(self, api_key: str, output_dir: Optional[Path] = None):
        """
        Initialize commentary generator.

        Args:
            api_key: Gemini API key
            output_dir: Directory to save commentary.json (default: project_root/output/)
        """
        self.client = genai.Client(api_key=api_key)
        self.context_manager = get_context_manager()

        if output_dir is None:
            # Default to project_root/output/
            output_dir = Path(__file__).parent.parent.parent.parent.parent / 'output'

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.commentary_file = self.output_dir / 'commentary.json'
        
        # Initialize graph nodes (lazy loaded only when use_graph=True)
        self._nodes = None
    
    def _get_nodes(self) -> List[CommentaryNode]:
        """Lazy load graph nodes."""
        if self._nodes is None:
            from .graph_nodes import (
                GoalNode, ReplayNode, CelebrationNode,
                SlowPlayNode, FastPlayNode
            )
            self._nodes = [
                # Priority nodes (checked first in _select_node)
                GoalNode(),
                ReplayNode(),
                CelebrationNode(),
                # Intensity-based nodes (fallback)
                SlowPlayNode(),
                FastPlayNode()
            ]
            print(f"[COMMENTARY] Initialized {len(self._nodes)} graph nodes: Goal, Replay, Celebration, SlowPlay, FastPlay")
        return self._nodes
    
    def _select_node(self, events: list, use_priority: bool = True) -> Optional[CommentaryNode]:
        """
        Select appropriate node based on events.
        
        Priority order (if use_priority=True):
        1. Goal Node (if goal detected)
        2. Replay Node (if replay flag set)
        3. Celebration Node (if celebration detected)
        4. Fast/Slow Play Node (intensity-based)
        
        Args:
            events: List of event dictionaries
            use_priority: If True, check for special events first
        
        Returns:
            Selected CommentaryNode or None if no events
        """
        if not events:
            return None
        
        nodes = self._get_nodes()
        
        # Priority routing for special events
        if use_priority:
            # Import special nodes for isinstance checks
            from .graph_nodes.goal_node import GoalNode
            from .graph_nodes.replay_node import ReplayNode
            from .graph_nodes.celebration_node import CelebrationNode
            
            # Check for goal (HIGHEST PRIORITY)
            if self._is_goal_event(events):
                goal_node = next((n for n in nodes if isinstance(n, GoalNode)), None)
                if goal_node:
                    print(f"  🎯 Special event: GOAL detected!")
                    print(f"  → Selected: {goal_node.get_style_name()}")
                    return goal_node
            
            # Check for replay
            if self._is_replay_event(events):
                replay_node = next((n for n in nodes if isinstance(n, ReplayNode)), None)
                if replay_node:
                    print(f"  🎯 Special event: REPLAY detected!")
                    print(f"  → Selected: {replay_node.get_style_name()}")
                    return replay_node
            
            # Check for celebration
            if self._is_celebration_event(events):
                celebration_node = next((n for n in nodes if isinstance(n, CelebrationNode)), None)
                if celebration_node:
                    print(f"  🎯 Special event: CELEBRATION detected!")
                    print(f"  → Selected: {celebration_node.get_style_name()}")
                    return celebration_node
        
        # Fallback to intensity-based routing
        intensities = [e.get('intensity', 5) for e in events]
        avg_intensity = sum(intensities) / len(intensities)
        
        print(f"  Average event intensity: {avg_intensity:.1f}/10")
        
        # Find matching node based on intensity
        for node in nodes:
            if node.should_activate(avg_intensity):
                print(f"  → Selected: {node.get_style_name()}")
                print(f"  → Intensity range: {node.get_intensity_range()}")
                return node
        
        # Fallback to first node
        return nodes[0]
    
    def _is_goal_event(self, events: list) -> bool:
        """
        Check if events contain a goal.
        
        Args:
            events: List of event dictionaries
        
        Returns:
            True if a goal is detected
        """
        for event in events:
            desc = event.get('description', '').lower()
            # Check for goal keywords or very high intensity
            if 'goal!' in desc or 'scores' in desc or event.get('intensity', 0) >= 9:
                return True
        return False
    
    def _is_replay_event(self, events: list) -> bool:
        """
        Check if events are replays.
        
        Args:
            events: List of event dictionaries
        
        Returns:
            True if any event is a replay
        """
        return any(event.get('replay', False) for event in events)
    
    def _is_celebration_event(self, events: list) -> bool:
        """
        Check if events are celebrations.
        
        Args:
            events: List of event dictionaries
        
        Returns:
            True if celebration detected
        """
        celebration_keywords = ['celebration', 'fireworks', 'erupts', 'crowd', 'fans', 'celebrates']
        for event in events:
            desc = event.get('description', '').lower()
            if any(keyword in desc for keyword in celebration_keywords):
                return True
        return False

    def _build_prompt(self, events: list, video_duration: float, use_graph: bool = False) -> str:
        """
        Build the prompt for commentary generation.

        Args:
            events: List of event dictionaries
            video_duration: Total video duration in seconds
            use_graph: If True, use graph-based node selection for intensity-aware commentary

        Returns:
            Complete prompt string
        """
        prompt_parts = []

        # Add match context if available
        context_text = self.context_manager.format_for_prompt()
        if context_text:
            prompt_parts.append(context_text)
            prompt_parts.append("")

        # Use graph node or standard prompt
        if use_graph:
            node = self._select_node(events)
            if node:
                # Add base system prompt
                prompt_parts.append(COMMENTARY_SYSTEM_PROMPT)
                prompt_parts.append("")
                # Add node-specific style modifier
                prompt_parts.append(node.get_system_prompt_modifier())
            else:
                # Fallback to standard if no node selected
                prompt_parts.append(COMMENTARY_SYSTEM_PROMPT)
        else:
            # Standard prompt (existing behavior)
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

    def generate_commentary(
        self,
        events: list,
        video_duration: float,
        use_streaming: bool = False,
        use_graph: bool = False
    ) -> List[Commentary]:
        """
        Generate commentary from detected events.

        Args:
            events: List of event dictionaries from events.json
            video_duration: Total video duration in seconds
            use_streaming: Whether to use streaming API (future enhancement)
            use_graph: Whether to use graph-based node selection (NEW)

        Returns:
            List of Commentary objects

        Raises:
            ValueError: If response is invalid
            RuntimeError: If API call fails
        """
        print(f"\n{'='*60}")
        print(f"🎙️  COMMENTARY GENERATION")
        if use_graph:
            print(f"📊 Mode: Graph-based (Intensity-aware)")
        else:
            print(f"📝 Mode: Standard")
        print(f"{'='*60}")
        print(f"Events to process: {len(events)}")
        print(f"Video duration: {seconds_to_time(video_duration)}")

        # Build prompt with optional graph routing
        prompt = self._build_prompt(events, video_duration, use_graph=use_graph)

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

            # Save to file
            self._save_commentaries(final_commentaries)

            print(f"\n{'='*60}")
            print(f"COMMENTARY GENERATION COMPLETED")
            print(f"{'='*60}")
            print(f"Total commentary segments: {len(final_commentaries)}")
            print(f"Commentaries saved to: {self.commentary_file}")

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

    def _save_commentaries(self, commentaries: List[Commentary]) -> None:
        """
        Save commentaries to commentary.json file.

        Args:
            commentaries: List of Commentary objects to save
        """
        commentary_output = CommentaryOutput(commentaries=commentaries)

        with open(self.commentary_file, 'w', encoding='utf-8') as f:
            json.dump(
                commentary_output.model_dump(),
                f,
                indent=2,
                ensure_ascii=False
            )

        print(f"[COMMENTARY] Saved {len(commentaries)} commentaries to {self.commentary_file}")

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
