"""
Pydantic models for dual-commentator football commentary output.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List


class CommentaryLine(BaseModel):
    """
    A single line of commentary spoken by one commentator.
    
    Attributes:
        speaker: Either "Lead" or "Co"
        line: The spoken commentary line
    """
    speaker: str = Field(..., description="Name of the speaker (e.g., 'Lead' or 'Co')")
    line: str = Field(..., description="Commentary line spoken by the commentator")


class Commentary(BaseModel):
    """
    Represents a single commentary segment with two interacting commentators.

    Attributes:
        start_time: Start timestamp in HH:MM:SS format
        end_time: End timestamp in HH:MM:SS format
        text: List of lines exchanged by Lead and Co commentators
    """
    start_time: str = Field(..., description="Start timestamp in HH:MM:SS format")
    end_time: str = Field(..., description="End timestamp in HH:MM:SS format")
    text: List[CommentaryLine] = Field(
        ..., 
        description="List of commentary lines (Lead and Co interaction)"
    )

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM:SS time format."""
        parts = v.split(':')
        if len(parts) != 3:
            raise ValueError(f"Time must be in HH:MM:SS format, got: {v}")
        try:
            hours, minutes, seconds = map(int, parts)
            if not (0 <= hours and 0 <= minutes < 60 and 0 <= seconds < 60):
                raise ValueError(f"Invalid time values in: {v}")
        except ValueError as e:
            raise ValueError(f"Invalid time format: {v}") from e
        return v


class CommentaryOutput(BaseModel):
    """
    Output model for dual-commentator commentary generation.
    """
    commentaries: List[Commentary] = Field(
        default_factory=list,
        description="List of commentary segments"
    )
