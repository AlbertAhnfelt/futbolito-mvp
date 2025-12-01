"""
Base node class for graph-based commentary generation.

All commentary nodes inherit from CommentaryNode.
"""

from abc import ABC, abstractmethod
from typing import Tuple


class CommentaryNode(ABC):
    """Base class for graph-based commentary nodes."""
    
    @abstractmethod
    def should_activate(self, avg_intensity: float) -> bool:
        """
        Check if this node should handle commentary for given intensity.
        
        Args:
            avg_intensity: Average intensity of events (1-10 scale)
        
        Returns:
            True if this node should be activated
        """
        pass
    
    @abstractmethod
    def get_system_prompt_modifier(self) -> str:
        """
        Get node-specific prompt additions/modifications.
        
        This text is appended to the base system prompt to modify
        the commentary style for this intensity range.
        
        Returns:
            Node-specific prompt modifier text
        """
        pass
    
    @abstractmethod
    def get_style_name(self) -> str:
        """
        Get human-readable style name.
        
        Returns:
            Style name for logging (e.g., "Analytical & Tactical")
        """
        pass
    
    @abstractmethod
    def get_intensity_range(self) -> Tuple[float, float]:
        """
        Get intensity range this node handles (min, max).
        
        Returns:
            Tuple of (min_intensity, max_intensity)
        """
        pass

