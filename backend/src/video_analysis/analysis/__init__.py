"""
Video analysis module for event detection.
Analyzes videos in 30-second intervals to detect football events.
"""

from .event_detector import EventDetector
from .models import Event, EventsOutput

__all__ = ['EventDetector', 'Event', 'EventsOutput']
