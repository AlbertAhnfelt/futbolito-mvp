"""
Graph nodes for different commentary styles and contexts.

Each node represents a specialized LLM prompt configuration
for specific game situations.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base_node import BaseNode
    from .slow_play_node import SlowPlayNode
    from .fast_play_node import FastPlayNode

__all__ = [
    'BaseNode',
    'SlowPlayNode', 
    'FastPlayNode',
]

