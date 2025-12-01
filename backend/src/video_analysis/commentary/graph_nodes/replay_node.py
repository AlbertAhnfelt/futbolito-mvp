"""
Replay Node - Analytical commentary for replay segments.

Provides expert analysis and detailed observation for replay moments.
"""

from typing import Tuple
from .base_node import CommentaryNode


class ReplayNode(CommentaryNode):
    """Analytical commentary for replay segments."""
    
    def should_activate(self, avg_intensity: float) -> bool:
        """
        Not activated by intensity alone.
        Replays are detected via replay flag in event data.
        """
        return False
    
    def get_intensity_range(self) -> Tuple[float, float]:
        """Return intensity range: varies (replays can be any intensity)."""
        return (1.0, 10.0)
    
    def get_style_name(self) -> str:
        """Return style name for logging."""
        return "Replay Analysis"
    
    def get_system_prompt_modifier(self) -> str:
        """Return replay analysis commentary style prompt."""
        return """
COMMENTARY STYLE: REPLAY ANALYSIS

This is a REPLAY segment. Your role is to provide expert analysis.

1. TONE: Analytical, reviewing, educational
2. FOCUS:
   - "Let's watch that again..." or "On the replay..."
   - Break down what happened step-by-step
   - Point out details missed in real-time
   - Use tactical vocabulary
3. PACING: Slower, methodical
4. LANGUAGE:
   - "Notice how...", "Watch as...", "If you look closely..."
   - Technical terminology
   - Frame-by-frame analysis

EXAMPLES:
- "Let's watch that again. Notice how Messi checks his shoulder before receiving, already knowing where the defender is..."
- "On the replay, you can see the goalkeeper was slightly off his line, giving Messi that extra yard of space..."

DO NOT: Create false excitement for something already seen.
"""

