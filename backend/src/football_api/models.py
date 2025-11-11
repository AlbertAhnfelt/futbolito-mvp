"""
Pydantic models for FBRApi data structures.
These models will be adapted once we have access to the actual API documentation.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class RosterPlayer(BaseModel):
    """Player in a team roster."""
    id: str
    name: str
    jersey_number: Optional[str] = None
    position: Optional[str] = None
    age: Optional[int] = None
    nationality: Optional[str] = None


class TeamSearchResult(BaseModel):
    """Simplified team info for search results."""
    id: str
    name: str
    country: Optional[str] = None
    league: Optional[str] = None
    logo_url: Optional[str] = None


class TeamDetails(BaseModel):
    """Detailed team information."""
    id: str
    name: str
    country: Optional[str] = None
    league: Optional[str] = None
    founded: Optional[int] = None
    stadium: Optional[str] = None
    logo_url: Optional[str] = None
    roster: List[RosterPlayer] = Field(default_factory=list)


class GameSearchResult(BaseModel):
    """Simplified game info for search results."""
    id: str
    home_team: str
    away_team: str
    home_team_id: str
    away_team_id: str
    date: str
    competition: Optional[str] = None
    status: Optional[str] = None  # e.g., "finished", "scheduled", "live"


class GameDetails(BaseModel):
    """Detailed game information including lineups."""
    id: str
    home_team: TeamSearchResult
    away_team: TeamSearchResult
    date: str
    competition: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    home_lineup: List[RosterPlayer] = Field(default_factory=list)
    away_lineup: List[RosterPlayer] = Field(default_factory=list)


class GameFilters(BaseModel):
    """Filters for game search."""
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    date_from: Optional[str] = None  # ISO format: YYYY-MM-DD
    date_to: Optional[str] = None
    competition: Optional[str] = None


class CachedResponse(BaseModel):
    """Wrapper for cached API responses."""
    timestamp: datetime
    data: dict
    ttl_hours: int = 24

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        from datetime import timedelta
        expiry_time = self.timestamp + timedelta(hours=self.ttl_hours)
        return datetime.now() > expiry_time
