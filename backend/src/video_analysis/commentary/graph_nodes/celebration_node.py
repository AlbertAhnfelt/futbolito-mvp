"""
Celebration Node - Atmospheric commentary for celebration moments.

Provides joyful, descriptive commentary for post-goal celebrations and crowd reactions.
"""

from typing import Tuple
from .base_node import CommentaryNode


class CelebrationNode(CommentaryNode):
    """Atmospheric commentary for celebrations."""
    
    def should_activate(self, avg_intensity: float) -> bool:
        """
        Not activated by intensity alone.
        Celebrations are detected via keyword detection in event descriptions.
        """
        return False
    
    def get_intensity_range(self) -> Tuple[float, float]:
        """Return typical celebration intensity range: 6.0 to 8.0."""
        return (6.0, 8.0)
    
    def get_style_name(self) -> str:
        """Return style name for logging."""
        return "Celebration & Atmosphere"
    
    def get_system_prompt_modifier(self) -> str:
        """Return celebration commentary style prompt."""
        return """
COMMENTARY STYLE: CELEBRATION & ATMOSPHERE

Describe the CELEBRATION and stadium atmosphere after a goal.

1. TONE: Joyful, atmospheric, descriptive
2. FOCUS:
   - Player celebrations
   - Crowd reactions
   - Fireworks, fan celebrations
   - Team spirit and emotion
3. PACING: Medium energy, describing the scene
4. LANGUAGE:
   - Descriptive, painting a picture
   - Emotional but not analytical
   - "The crowd erupts!", "Pandemonium!", "Pure joy!"

EXAMPLES:
- "The stadium explodes in celebration! Fireworks lighting up the Miami sky!"
- "Look at the joy on Messi's face as his teammates mob him!"
- "The fans are going absolutely wild! What a moment!"

DO NOT: Analyze tactics during celebration moments.
"""

