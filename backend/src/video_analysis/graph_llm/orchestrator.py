"""
Graph orchestrator for dynamic commentary generation.

Routes video segments to appropriate nodes based on game pace and intensity.
"""

import json
from typing import List, Dict
from google import genai
from google.genai import types
from pydantic import BaseModel

from .pace_detector import PaceDetector, VideoSegment
from .nodes.base_node import BaseNode, NodeInput, NodeOutput
from .nodes.slow_play_node import SlowPlayNode
from .nodes.fast_play_node import FastPlayNode


class CommentaryResponse(BaseModel):
    """Response from a node's commentary generation."""
    description: str
    commentary: str


class GraphOrchestrator:
    """
    Orchestrates the graph-based LLM system.
    
    Flow:
    1. Detect video pace/intensity (PaceDetector)
    2. Route segments to appropriate nodes
    3. Generate commentary for each segment
    4. Aggregate and return results
    """
    
    def __init__(self, api_key: str):
        """
        Initialize orchestrator.
        
        Args:
            api_key: Google Gemini API key
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.pace_detector = PaceDetector(api_key=api_key)
        
        # Initialize nodes
        self.nodes: List[BaseNode] = [
            SlowPlayNode(api_key=api_key),
            FastPlayNode(api_key=api_key),
        ]
        
        print(f"🎬 Graph Orchestrator initialized with {len(self.nodes)} nodes")
    
    def process_video(self, file_uri: str) -> tuple[List[NodeOutput], Dict]:
        """
        Process entire video through the graph system.
        
        Args:
            file_uri: Gemini file URI for the uploaded video
        
        Returns:
            Tuple of (list of NodeOutput objects, metadata dict)
        """
        print("\n" + "="*60)
        print("🎬 Starting Graph-Based Commentary Generation")
        print("="*60)
        
        # Step 1: Detect pace/intensity
        print("\n📊 Step 1: Analyzing video pace...")
        segments = self.pace_detector.analyze_pace(file_uri)
        
        if not segments:
            raise ValueError("No segments detected from video")
        
        # Step 2: Route segments and generate commentary
        print(f"\n🎯 Step 2: Routing {len(segments)} segments to nodes...")
        outputs = []
        node_usage = {}
        
        for i, segment in enumerate(segments):
            print(f"\n   Segment {i+1}/{len(segments)}: "
                  f"{segment.start_time}-{segment.end_time} "
                  f"(intensity: {segment.intensity}/10, type: {segment.event_type})")
            
            # Select appropriate node
            selected_node = self._select_node(segment.intensity)
            node_name = selected_node.__class__.__name__
            node_usage[node_name] = node_usage.get(node_name, 0) + 1
            
            print(f"   → Routed to: {node_name}")
            
            # Generate commentary using selected node
            try:
                output = self._generate_commentary(segment, selected_node, file_uri)
                outputs.append(output)
                print(f"   ✅ Commentary generated ({len(output.commentary)} chars)")
            except Exception as e:
                print(f"   ⚠️  Failed: {str(e)}")
                # Create fallback output
                outputs.append(NodeOutput(
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    description=segment.description,
                    commentary=f"Action at {segment.start_time}",
                    node_used=node_name,
                    intensity=segment.intensity
                ))
        
        # Calculate metadata
        metadata = {
            'total_segments': len(segments),
            'nodes_used': node_usage,
            'avg_intensity': sum(s.intensity for s in segments) / len(segments),
            'intensity_distribution': self._get_intensity_distribution(segments)
        }
        
        print("\n" + "="*60)
        print("✅ Graph Processing Complete")
        print(f"   Segments: {len(outputs)}")
        print(f"   Node usage: {node_usage}")
        print(f"   Avg intensity: {metadata['avg_intensity']:.1f}/10")
        print("="*60 + "\n")
        
        return outputs, metadata
    
    def _select_node(self, intensity: int) -> BaseNode:
        """
        Select appropriate node based on intensity.
        
        Args:
            intensity: Intensity score (0-10)
        
        Returns:
            Selected node
        """
        for node in self.nodes:
            if node.should_activate(intensity):
                return node
        
        # Fallback to first node if none match
        return self.nodes[0]
    
    def _generate_commentary(
        self,
        segment: VideoSegment,
        node: BaseNode,
        file_uri: str
    ) -> NodeOutput:
        """
        Generate commentary for a segment using specified node.
        
        Args:
            segment: Video segment to analyze
            node: Node to use for generation
            file_uri: Gemini file URI
        
        Returns:
            NodeOutput with generated commentary
        """
        # Prepare node input
        node_input = NodeInput(
            segment_start=segment.start_time,
            segment_end=segment.end_time,
            intensity=segment.intensity,
            event_type=segment.event_type,
            description=segment.description,
            file_uri=file_uri
        )
        
        # Get node-specific prompt
        prompt = node.get_prompt(node_input)
        
        # Call Gemini with the prompt
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
                "response_schema": CommentaryResponse,
            }
        )
        
        # Parse response
        commentary_data = json.loads(response.text)
        
        # Create output
        return NodeOutput(
            start_time=segment.start_time,
            end_time=segment.end_time,
            description=commentary_data['description'],
            commentary=commentary_data['commentary'],
            node_used=node.__class__.__name__,
            intensity=segment.intensity
        )
    
    @staticmethod
    def _get_intensity_distribution(segments: List[VideoSegment]) -> Dict[str, int]:
        """Calculate distribution of intensity levels."""
        distribution = {
            'slow (0-3)': 0,
            'medium (4-6)': 0,
            'high (7-8)': 0,
            'very_high (9-10)': 0
        }
        
        for seg in segments:
            if seg.intensity <= 3:
                distribution['slow (0-3)'] += 1
            elif seg.intensity <= 6:
                distribution['medium (4-6)'] += 1
            elif seg.intensity <= 8:
                distribution['high (7-8)'] += 1
            else:
                distribution['very_high (9-10)'] += 1
        
        return distribution


