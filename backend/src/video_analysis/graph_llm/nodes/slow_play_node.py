"""
Slow Play Node - Analytical commentary for slower game moments.

Handles low-intensity periods with tactical analysis and detailed observation.
"""

from .base_node import BaseNode, NodeInput


class SlowPlayNode(BaseNode):
    """
    Node for slow, analytical commentary during low-intensity play.
    
    Activated when: intensity <= 5
    Style: Measured, analytical, tactical
    Focus: Build-up play, positioning, patterns, previous actions
    """
    
    def should_activate(self, intensity: int) -> bool:
        """Activate for low-intensity play (0-5)."""
        return intensity <= 5
    
    def get_commentary_style(self) -> str:
        """Return commentary style description."""
        return "Analytical and tactical"
    
    def get_prompt(self, node_input: NodeInput) -> str:
        """
        Generate analytical prompt for slow play moments.
        
        Returns prompt that encourages tactical analysis and detailed observation.
        """
        duration_seconds = self._estimate_duration(node_input.segment_start, node_input.segment_end)
        max_words = int(duration_seconds * 2.5)  # Conservative word rate
        
        prompt = f"""
Analyze this specific segment of a football match from {node_input.segment_start} to {node_input.segment_end}.

CONTEXT:
- Pace: SLOW/MEASURED (intensity: {node_input.intensity}/10)
- Event type: {node_input.event_type}
- What's visible: {node_input.description}

YOUR ROLE: You are an analytical football commentator during a SLOWER moment of play.
This is NOT a high-action moment - take your time to provide insight.

TASK: Provide TWO types of analysis:

1. **description**: Technical analysis of what's happening
   - Focus on: formations, positioning, tactical intent, player decisions
   - Mention: passing patterns, space creation, defensive shape
   - Be specific about what you observe visually
   - Example: "The center-back drops deep to collect, drawing the press forward and creating space in behind for the midfielder to exploit."

2. **commentary**: TV commentator style - analytical and informative
   - Tone: Measured, thoughtful, educational
   - Style: Like watching with a tactical expert who explains patterns
   - Can reference: team strategy, player qualities, build-up patterns
   - Length: Maximum {max_words} words (pace yourself, you have time)
   - Example: "Notice how they're patient in possession here, working the ball from side to side. The left-back is staying high, providing width, while the defensive midfielder drops between the center-backs. Classic positional play, creating numerical advantages in the build-up."

VISUAL ANALYSIS ONLY: Base everything on what you SEE - player movements, positions, ball trajectory, body language.

Return ONLY valid JSON with "description" and "commentary" fields. No other text.
"""
        return prompt
    
    @staticmethod
    def _estimate_duration(start_time: str, end_time: str) -> float:
        """Estimate duration in seconds from time strings."""
        def time_to_seconds(time_str: str) -> float:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = int(parts[0]), float(parts[1])
                return m * 60 + s
            else:
                return float(parts[0])
        
        try:
            return time_to_seconds(end_time) - time_to_seconds(start_time)
        except:
            return 10.0  # Default fallback

