"""
Fast Play Node - Exciting commentary for high-intensity moments.

Provides energetic, urgent commentary during fast-paced, exciting play.
"""

from typing import Tuple
from .base_node import CommentaryNode


class FastPlayNode(CommentaryNode):
    """Exciting commentary for high-intensity play."""
    
    def should_activate(self, avg_intensity: float) -> bool:
        """Activate for high-intensity play (6-10 on 10-point scale)."""
        return avg_intensity > 5.0
    
    def get_intensity_range(self) -> Tuple[float, float]:
        """Return intensity range: 6.0 to 10.0."""
        return (6.0, 10.0)
    
    def get_style_name(self) -> str:
        """Return style name for logging."""
        return "Exciting & Urgent"
    
    def get_system_prompt_modifier(self) -> str:
        """Return exciting commentary style prompt."""
        return """
COMMENTARY STYLE: EXCITING & URGENT

This is a HIGH-INTENSITY moment! Your commentary should be:

1. TONE: Energetic, urgent, exciting
2. FOCUS:
   - Fast action and movement
   - Dangerous attacking plays
   - Critical moments and chances
   - Momentum and urgency
3. PACING: Quick, punchy, dramatic
4. LANGUAGE:
   - Short, impactful sentences
   - Action verbs
   - Build tension and excitement
   - Match the energy of the play

INTENSITY LEVELS:
- 6-7: "They're pushing forward! Dangerous position!"
- 8-9: "He's through! One-on-one! This is it!"
- 10: "GOAL! What a finish! Incredible!"

DO NOT: Be overly calm or analytical during exciting moments.
"""

