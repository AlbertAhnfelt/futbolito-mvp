"""
Goal Node - Maximum excitement commentary for goal moments.

Provides explosive, celebratory commentary when goals are scored.
"""

from typing import Tuple
from .base_node import CommentaryNode


class GoalNode(CommentaryNode):
    """Maximum excitement commentary for goals."""
    
    def should_activate(self, avg_intensity: float) -> bool:
        """
        Not activated by intensity alone.
        Goals are detected via event description inspection in _select_node().
        """
        return False
    
    def get_intensity_range(self) -> Tuple[float, float]:
        """Return typical goal intensity range: 9.0 to 10.0."""
        return (9.0, 10.0)
    
    def get_style_name(self) -> str:
        """Return style name for logging."""
        return "Goal Celebration"
    
    def get_system_prompt_modifier(self) -> str:
        """Return goal celebration commentary style prompt."""
        return """
COMMENTARY STYLE: GOAL CELEBRATION

A GOAL has been scored! This is the MOST exciting moment in football!

1. TONE: MAXIMUM excitement, explosive energy
2. DELIVERY:
   - Start with dramatic exclamation: "GOAL!", "IT'S IN!", "SCORES!"
   - Identify the scorer immediately
   - Describe the technique used
   - Build the narrative of the goal
3. STRUCTURE:
   - Burst of excitement (2-3 words)
   - Scorer identification
   - How the goal was scored
   - Context (score, importance)
4. LANGUAGE:
   - Superlatives ("incredible", "magnificent", "sensational")
   - Short, punchy sentences
   - Vary exclamation marks

EXAMPLES:
- "GOAL! Messi! What a finish! The Argentine maestro strikes again!"
- "IT'S IN! Ronaldo with the header! Unstoppable from six yards!"
- "SCORES! A thunderous strike into the top corner! Goalkeeper had no chance!"

DO NOT: Be calm, analytical, or understated. This is PURE EXCITEMENT!
"""

