"""
Base node class for graph LLM architecture.

All commentary nodes inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class NodeInput(BaseModel):
    """Input data for a node."""
    segment_start: str
    segment_end: str
    intensity: int
    event_type: str
    description: str
    file_uri: str  # Gemini file URI
    context: Optional[str] = ""  # Match context (team/player info)


class NodeOutput(BaseModel):
    """Output data from a node."""
    start_time: str
    end_time: str
    description: str  # Technical analysis
    commentary: str  # TV-style commentary
    node_used: str  # Which node generated this
    intensity: int  # Original intensity score


class BaseNode(ABC):
    """
    Abstract base class for all graph nodes.
    
    Each node represents a specialized LLM prompt configuration
    for specific game situations (e.g., slow play, fast play).
    """
    
    def __init__(self, api_key: str):
        """
        Initialize node.
        
        Args:
            api_key: Google Gemini API key
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        
        self.api_key = api_key
        self.node_name = self.__class__.__name__
    
    @abstractmethod
    def get_prompt(self, node_input: NodeInput) -> str:
        """
        Generate the prompt for this node type.
        
        Args:
            node_input: Input data for the segment
        
        Returns:
            Formatted prompt string
        """
        pass
    
    @abstractmethod
    def should_activate(self, intensity: int) -> bool:
        """
        Determine if this node should be activated for given intensity.
        
        Args:
            intensity: Intensity score (0-10)
        
        Returns:
            True if this node should handle the segment
        """
        pass
    
    @abstractmethod
    def get_commentary_style(self) -> str:
        """
        Get the commentary style description for this node.
        
        Returns:
            Description of commentary style
        """
        pass
    
    def __repr__(self) -> str:
        """String representation of the node."""
        return f"{self.node_name}(style='{self.get_commentary_style()}')"

