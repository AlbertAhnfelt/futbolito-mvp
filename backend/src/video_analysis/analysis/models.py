"""
Pydantic models for event detection output.
"""

from pydantic import BaseModel, Field
from typing import List


class Event(BaseModel):
    """
    Represents a single football event detected in the video.

    Attributes:
        time: Timestamp in HH:MM:SS format
        description: Detailed technical description of the event
        replay: Whether this is a replay (true) or live action (false)
        intensity: Intensity rating from 1 (calm) to 10 (very intense)
    """
    time: str = Field(..., description="Event timestamp in HH:MM:SS format")
    description: str = Field(..., description="Detailed technical description of the event")
    replay: bool = Field(..., description="true if replay, false if live action")
    intensity: int = Field(..., ge=1, le=10, description="Intensity rating from 1 to 10")


class EventsOutput(BaseModel):
    """
    Output model for event detection containing a list of events.
    """
    events: List[Event] = Field(default_factory=list, description="List of detected events")
