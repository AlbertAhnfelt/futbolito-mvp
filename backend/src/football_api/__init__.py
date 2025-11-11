"""
Football API integration module for FBRApi.
Provides team search, game search, and roster management functionality.
"""

from .client import FBRApiClient
from .service import FootballService
from .models import (
    TeamSearchResult,
    TeamDetails,
    GameSearchResult,
    GameDetails,
    RosterPlayer,
    GameFilters,
)

__all__ = [
    "FBRApiClient",
    "FootballService",
    "TeamSearchResult",
    "TeamDetails",
    "GameSearchResult",
    "GameDetails",
    "RosterPlayer",
    "GameFilters",
]
