"""
Pydantic models for commentary generation output.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Literal


class Commentary(BaseModel):
    """
    Represents a single commentary segment with speaker identification.

    Attributes:
        start_time: Start timestamp in HH:MM:SS format
        end_time: End timestamp in HH:MM:SS format
        commentary: The commentary text (max 2.5 words/second)
        speaker: Which commentator is speaking (COMMENTATOR_1 or COMMENTATOR_2)
    """
    start_time: str = Field(..., description="Start timestamp in HH:MM:SS format", pattern=r"^[0-9]{2}:[0-5][0-9]:[0-5][0-9]$")
    end_time: str = Field(..., description="End timestamp in HH:MM:SS format", pattern=r"^[0-9]{2}:[0-5][0-9]:[0-5][0-9]$")
    commentary: str = Field(..., description="Commentary text")
    speaker: Literal["COMMENTATOR_1", "COMMENTATOR_2"] = Field(
        ..., 
        description="Which commentator is speaking"
    )

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM:SS format."""
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
    Output model for commentary generation containing a list of commentary segments.
    """
    commentaries: List[Commentary] = Field(
        default_factory=list, 
        description="List of commentary segments with speaker identification"
    )