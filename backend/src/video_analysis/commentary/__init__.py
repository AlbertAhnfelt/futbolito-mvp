"""
Commentary generation module.
Generates football commentary from detected events using streaming.
"""

from .commentary_generator import CommentaryGenerator
from .models import Commentary, CommentaryOutput

__all__ = ['CommentaryGenerator', 'Commentary', 'CommentaryOutput']
