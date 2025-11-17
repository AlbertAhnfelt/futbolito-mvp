"""
Fast Play Node - Exciting commentary for high-intensity moments.

Handles high-intensity periods with urgent, energetic play-by-play.
"""

from .base_node import BaseNode, NodeInput


class FastPlayNode(BaseNode):
    """
    Node for exciting, urgent commentary during high-intensity play.
    
    Activated when: intensity > 5
    Style: Energetic, urgent, play-by-play
    Focus: Action description, excitement, momentum
    """
    
    def should_activate(self, intensity: int) -> bool:
        """Activate for high-intensity play (6-10)."""
        return intensity > 5
    
    def get_commentary_style(self) -> str:
        """Return commentary style description."""
        return "Exciting and urgent"
    
    def get_prompt(self, node_input: NodeInput) -> str:
        """
        Generate exciting prompt for fast play moments.
        
        Returns prompt that encourages energetic, urgent commentary.
        """
        duration_seconds = self._estimate_duration(node_input.segment_start, node_input.segment_end)
        max_words = int(duration_seconds * 2.5)  # Conservative word rate
        
        # Adjust excitement level based on intensity
        if node_input.intensity >= 9:
            intensity_desc = "EXTREME - Goal, shot, or critical moment"
            tone_guide = "MAXIMUM excitement, short sharp bursts, single exclamations"
        elif node_input.intensity >= 7:
            intensity_desc = "HIGH - Fast attack or dangerous play"
            tone_guide = "High energy, urgent, building tension"
        else:
            intensity_desc = "MEDIUM-HIGH - Quick transition or pressing"
            tone_guide = "Energetic but controlled, describe the action"
        
        prompt = f"""
Analyze this specific segment of a football match from {node_input.segment_start} to {node_input.segment_end}.

CONTEXT:
- Pace: FAST/INTENSE (intensity: {node_input.intensity}/10 - {intensity_desc})
- Event type: {node_input.event_type}
- What's visible: {node_input.description}

YOUR ROLE: You are an energetic football commentator during a HIGH-ACTION moment.
This is EXCITING - match the energy of the play!

TASK: Provide TWO types of analysis:

1. **description**: Quick technical analysis of the action
   - Focus on: speed of play, attacking movements, defensive reactions
   - Mention: key passes, shots, tackles, positioning in dangerous areas
   - Be concise but precise
   - Example: "Rapid counterattack down the right channel, striker making diagonal run into the box, defender scrambling to recover."

2. **commentary**: TV commentator style - EXCITING and urgent
   - Tone: {tone_guide}
   - Style: Like a commentator when something thrilling is happening
   - Energy: Match the intensity level - higher intensity = MORE excitement!
   - Length: Maximum {max_words} words (keep it tight and punchy!)
   - Use short sentences for drama
   - Examples by intensity:
     * 6-7: "Quick transition! They're breaking forward with numbers! Can they capitalize here?"
     * 8-9: "He's through! One-on-one with the keeper! This is it! SHOOTS!"
     * 10: "GOAL! Incredible finish! What a moment!"

VISUAL ANALYSIS ONLY: Base everything on what you SEE - speed of movement, urgency, reactions, ball trajectory.

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


