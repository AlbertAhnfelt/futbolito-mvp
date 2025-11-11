"""
Service layer for football API with JSON file caching.
Handles business logic and caching of API responses.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .client import FBRApiClient
from .models import (
    TeamSearchResult,
    TeamDetails,
    GameSearchResult,
    GameDetails,
    GameFilters,
    RosterPlayer,
    CachedResponse,
)


class FootballService:
    """Service for managing football API operations with caching."""

    def __init__(self, cache_dir: str = "backend/data"):
        """
        Initialize the football service.

        Args:
            cache_dir: Directory to store cache files
        """
        self.client = FBRApiClient()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache file paths
        self.teams_cache_file = self.cache_dir / "teams_cache.json"
        self.games_cache_file = self.cache_dir / "games_cache.json"
        self.rosters_cache_file = self.cache_dir / "rosters_cache.json"

        # Initialize cache files if they don't exist
        self._init_cache_files()

    def _init_cache_files(self):
        """Initialize cache files if they don't exist."""
        for cache_file in [self.teams_cache_file, self.games_cache_file, self.rosters_cache_file]:
            if not cache_file.exists():
                cache_file.write_text("{}")

    def _load_cache(self, cache_file: Path) -> Dict[str, Any]:
        """Load cache from file."""
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_cache(self, cache_file: Path, cache_data: Dict[str, Any]):
        """Save cache to file."""
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

    def _get_cached_data(self, cache_file: Path, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data if it exists and hasn't expired.

        Args:
            cache_file: Path to cache file
            key: Cache key

        Returns:
            Cached data or None if expired/not found
        """
        cache = self._load_cache(cache_file)

        if key not in cache:
            return None

        try:
            cached_response = CachedResponse(**cache[key])
            if cached_response.is_expired():
                # Remove expired entry
                del cache[key]
                self._save_cache(cache_file, cache)
                return None

            return cached_response.data
        except Exception:
            return None

    def _set_cached_data(self, cache_file: Path, key: str, data: Dict[str, Any], ttl_hours: int = 24):
        """
        Store data in cache.

        Args:
            cache_file: Path to cache file
            key: Cache key
            data: Data to cache
            ttl_hours: Time to live in hours
        """
        cache = self._load_cache(cache_file)

        cached_response = CachedResponse(
            timestamp=datetime.now(),
            data=data,
            ttl_hours=ttl_hours,
        )

        cache[key] = cached_response.model_dump(mode="json")
        self._save_cache(cache_file, cache)

    async def search_teams(self, query: str, use_cache: bool = True) -> List[TeamSearchResult]:
        """
        Search for teams by name with caching.

        Args:
            query: Search query
            use_cache: Whether to use cached data

        Returns:
            List of matching teams
        """
        cache_key = f"search_{query.lower()}"

        # Check cache
        if use_cache:
            cached_data = self._get_cached_data(self.teams_cache_file, cache_key)
            if cached_data:
                return [TeamSearchResult(**team) for team in cached_data]

        # Fetch from API
        teams = await self.client.search_teams(query)

        # Cache the results
        self._set_cached_data(
            self.teams_cache_file,
            cache_key,
            [team.model_dump() for team in teams],
        )

        return teams

    async def get_team(self, team_id: str, use_cache: bool = True) -> TeamDetails:
        """
        Get detailed team information with caching.

        Args:
            team_id: Team ID
            use_cache: Whether to use cached data

        Returns:
            Detailed team information
        """
        cache_key = f"team_{team_id}"

        # Check cache
        if use_cache:
            cached_data = self._get_cached_data(self.teams_cache_file, cache_key)
            if cached_data:
                return TeamDetails(**cached_data)

        # Fetch from API
        team = await self.client.get_team(team_id)

        # Cache the result
        self._set_cached_data(
            self.teams_cache_file,
            cache_key,
            team.model_dump(),
        )

        return team

    async def search_games(self, filters: GameFilters, use_cache: bool = True) -> List[GameSearchResult]:
        """
        Search for games with caching.

        Args:
            filters: Game search filters
            use_cache: Whether to use cached data

        Returns:
            List of matching games
        """
        # Create cache key from filters
        cache_key = f"search_{filters.model_dump_json()}"

        # Check cache
        if use_cache:
            cached_data = self._get_cached_data(self.games_cache_file, cache_key)
            if cached_data:
                return [GameSearchResult(**game) for game in cached_data]

        # Fetch from API
        games = await self.client.search_games(filters)

        # Cache the results (shorter TTL for games as they update more frequently)
        self._set_cached_data(
            self.games_cache_file,
            cache_key,
            [game.model_dump() for game in games],
            ttl_hours=6,  # Shorter cache time for games
        )

        return games

    async def get_game(self, game_id: str, use_cache: bool = True) -> GameDetails:
        """
        Get detailed game information with caching.

        Args:
            game_id: Game ID
            use_cache: Whether to use cached data

        Returns:
            Detailed game information
        """
        cache_key = f"game_{game_id}"

        # Check cache
        if use_cache:
            cached_data = self._get_cached_data(self.games_cache_file, cache_key)
            if cached_data:
                return GameDetails(**cached_data)

        # Fetch from API
        game = await self.client.get_game(game_id)

        # Cache the result
        self._set_cached_data(
            self.games_cache_file,
            cache_key,
            game.model_dump(),
            ttl_hours=6,
        )

        return game

    async def get_roster(self, team_id: str, use_cache: bool = True) -> List[RosterPlayer]:
        """
        Get team roster with caching.

        Args:
            team_id: Team ID
            use_cache: Whether to use cached data

        Returns:
            List of players in roster
        """
        cache_key = f"roster_{team_id}"

        # Check cache
        if use_cache:
            cached_data = self._get_cached_data(self.rosters_cache_file, cache_key)
            if cached_data:
                return [RosterPlayer(**player) for player in cached_data]

        # Fetch from API
        roster = await self.client.get_roster(team_id)

        # Cache the results
        self._set_cached_data(
            self.rosters_cache_file,
            cache_key,
            [player.model_dump() for player in roster],
        )

        return roster

    def clear_cache(self, cache_type: Optional[str] = None):
        """
        Clear cache files.

        Args:
            cache_type: Type of cache to clear ('teams', 'games', 'rosters', or None for all)
        """
        if cache_type == "teams" or cache_type is None:
            self.teams_cache_file.write_text("{}")

        if cache_type == "games" or cache_type is None:
            self.games_cache_file.write_text("{}")

        if cache_type == "rosters" or cache_type is None:
            self.rosters_cache_file.write_text("{}")


# Global service instance
_service: Optional[FootballService] = None


def get_football_service() -> FootballService:
    """Get or create the global football service instance."""
    global _service
    if _service is None:
        _service = FootballService()
    return _service
