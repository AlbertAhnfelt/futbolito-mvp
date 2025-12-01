"""
Slow Play Node - Analytical commentary for low-intensity moments.

Provides tactical analysis and detailed observation during slower periods of play.
"""

from typing import Tuple
from .base_node import CommentaryNode


class SlowPlayNode(CommentaryNode):
    """Analytical commentary for low-intensity play."""
    
    def should_activate(self, avg_intensity: float) -> bool:
        """Activate for low-intensity play (1-5 on 10-point scale)."""
        return avg_intensity <= 5.0
    
    def get_intensity_range(self) -> Tuple[float, float]:
        """Return intensity range: 1.0 to 5.0."""
        return (1.0, 5.0)
    
    def get_style_name(self) -> str:
        """Return style name for logging."""
        return "Analytical & Tactical"
    
    def get_system_prompt_modifier(self) -> str:
        """Return analytical commentary style prompt."""
        return """
COMMENTARY STYLE: ANALYTICAL & TACTICAL

This is a SLOWER, more measured moment in the match. Your commentary should be:

1. TONE: Calm, analytical, educational
2. FOCUS: 
   - Tactical positioning and formations
   - Build-up play patterns
   - Player decision-making
   - Team strategy
3. PACING: Take your time, you have room to explain
4. LANGUAGE: 
   - Use tactical terminology
   - Explain "why" players make certain moves
   - Reference patterns and strategies

EXAMPLE STYLE:
"Notice how the center-back drops deep to collect the ball, drawing the press forward 
and creating space in the midfield. The team is being patient here, working the ball 
from side to side, looking for an opening in the defensive line."

DO NOT: Rush, shout, or create artificial excitement for calm moments.
"""

