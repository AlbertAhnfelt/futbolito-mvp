"""
Video pace detection and intensity analysis.

Analyzes football video segments to determine game pace and intensity
for dynamic commentary generation.
"""

import json
from typing import List
from pydantic import BaseModel
from google import genai
from google.genai import types


class VideoSegment(BaseModel):
    """Represents a segment of video with pace information."""
    start_time: str
    end_time: str
    intensity: int  # 0-10 scale (0=very slow, 10=very intense)
    event_type: str  # e.g., "possession", "counterattack", "shot", "tackle"
    description: str  # Brief technical description


class PaceDetector:
    """
    Analyzes video to detect game pace and intensity.
    
    Uses Gemini to break down video into segments and classify
    each segment's intensity level.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize pace detector.
        
        Args:
            api_key: Google Gemini API key
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        self.client = genai.Client(api_key=api_key)
    
    def analyze_pace(self, file_uri: str) -> List[VideoSegment]:
        """
        Analyze video and return segments with pace classification.
        
        Args:
            file_uri: URI of uploaded video file in Gemini
        
        Returns:
            List of VideoSegment objects with intensity classification
        """
        prompt = """
Analyze this football match video and break it down into segments based on game pace and intensity.

For each distinct segment, provide:
1. **start_time** and **end_time** in HH:MM:SS or MM:SS format
2. **intensity** (0-10 scale):
   - 0-3: Very slow (ball out of play, stoppages, throw-ins, slow build-up)
   - 4-6: Medium (controlled possession, organized attack building)
   - 7-8: High (fast attacks, dangerous plays, pressing)
   - 9-10: Very high (shots, goals, near-misses, crucial moments)
3. **event_type**: Choose from: "stoppage", "slow_buildup", "possession", "buildup_attack", "counterattack", "dangerous_attack", "shot", "goal", "tackle", "save"
4. **description**: Brief technical description of what's happening

IMPORTANT GUIDELINES:
- Divide the video into 5-15 second segments (shorter for intense moments, longer for slow play)
- Base intensity ONLY on visual cues: player movement speed, ball speed, number of players involved, urgency
- High intensity = fast movement, quick passes, players running, crowded penalty area
- Low intensity = slow movement, backward passes, players walking, spread out formation

Return ONLY valid JSON. No other text.
"""
        
        try:
            response = self.client.models.generate_content(
                model='models/gemini-2.5-flash',
                contents=types.Content(
                    parts=[
                        types.Part(file_data=types.FileData(file_uri=file_uri)),
                        types.Part(text=prompt)
                    ]
                ),
                config={
                    "response_mime_type": "application/json",
                    "response_schema": list[VideoSegment],
                }
            )
            
            # Parse response
            segments_data = json.loads(response.text)
            segments = [VideoSegment(**seg) for seg in segments_data]
            
            # Log summary
            print(f"\n📊 Pace Detection Summary:")
            print(f"   Total segments: {len(segments)}")
            
            intensity_counts = {}
            for seg in segments:
                intensity_range = self._get_intensity_range(seg.intensity)
                intensity_counts[intensity_range] = intensity_counts.get(intensity_range, 0) + 1
            
            for range_name, count in sorted(intensity_counts.items()):
                print(f"   {range_name}: {count} segments")
            
            avg_intensity = sum(s.intensity for s in segments) / len(segments) if segments else 0
            print(f"   Average intensity: {avg_intensity:.1f}/10\n")
            
            return segments
        
        except Exception as e:
            print(f"⚠️  Pace detection failed: {str(e)}")
            # Return single segment covering whole video as fallback
            return [VideoSegment(
                start_time="00:00:00",
                end_time="00:10:00",
                intensity=5,
                event_type="possession",
                description="Full video (pace detection failed)"
            )]
    
    @staticmethod
    def _get_intensity_range(intensity: int) -> str:
        """Convert intensity score to human-readable range."""
        if intensity <= 3:
            return "Slow (0-3)"
        elif intensity <= 6:
            return "Medium (4-6)"
        elif intensity <= 8:
            return "High (7-8)"
        else:
            return "Very High (9-10)"


