"""
HTTP client for Football-Data.org API.
Documentation: https://www.football-data.org/documentation/api
"""

import os
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from difflib import SequenceMatcher
import httpx
from .models import (
    TeamSearchResult,
    TeamDetails,
    GameSearchResult,
    GameDetails,
    GameFilters,
    RosterPlayer,
)


class FootballDataClient:
    """Client for interacting with the Football-Data.org API."""

    def __init__(self):
        """Initialize the Football-Data.org API client."""
        self.base_url = "http://api.football-data.org/v4"
        self.api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
        self.timeout = 30.0

        # For now, we'll use mock mode if no API key is provided
        self.mock_mode = not self.api_key

        # Cache for team name to ID mappings
        self._team_cache: Dict[str, Dict[str, Any]] = {}

        # Cache for competitions
        self._competitions_cache: List[Dict[str, Any]] = []

        # Rate limiting: Free tier allows 10 requests/minute
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = 6.5  # ~10 requests per minute with buffer

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for API requests."""
        headers = {
            "Accept": "application/json",
        }

        if self.api_key:
            # Football-Data.org uses X-Auth-Token header
            headers["X-Auth-Token"] = self.api_key

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to the API."""
        if self.mock_mode:
            return self._get_mock_response(endpoint, params)

        # Rate limiting: Wait if needed
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            if elapsed < self._min_request_interval:
                wait_time = self._min_request_interval - elapsed
                await asyncio.sleep(wait_time)

        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                self._last_request_time = datetime.now()
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self._get_headers(),
                    params=params,
                    json=json_data,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                raise Exception(f"API request failed: {e.response.status_code} - {e.response.text}")
            except httpx.RequestError as e:
                raise Exception(f"Request error: {str(e)}")

    def _get_mock_response(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return mock data for testing without API key."""
        # Mock data for different endpoints
        if "/teams/search" in endpoint or "/competitions/" in endpoint and "/teams" in endpoint:
            query = params.get("query", "") if params else ""
            return {
                "teams": [
                    {
                        "id": 86,
                        "name": f"FC {query.title()} United",
                        "shortName": f"{query.title()} United",
                        "tla": "FCU",
                        "crest": None,
                        "address": "Mock Address",
                        "website": "http://mockteam.com",
                        "founded": 1899,
                        "clubColors": "Red / White",
                        "venue": "Mock Stadium",
                    },
                    {
                        "id": 87,
                        "name": f"{query.title()} City",
                        "shortName": f"{query.title()} City",
                        "tla": "MCC",
                        "crest": None,
                        "address": "Mock Address 2",
                        "website": "http://mockcity.com",
                        "founded": 1900,
                        "clubColors": "Blue / White",
                        "venue": "City Stadium",
                    },
                ]
            }

        elif endpoint.startswith("/teams/"):
            return {
                "id": 86,
                "name": "Mock Team FC",
                "shortName": "Mock FC",
                "tla": "MFC",
                "crest": None,
                "address": "Mock Address",
                "website": "http://mockteam.com",
                "founded": 1899,
                "clubColors": "Red / White",
                "venue": "Mock Stadium",
                "squad": [
                    {
                        "id": 1,
                        "name": "John Doe",
                        "position": "Offence",
                        "dateOfBirth": "1995-01-15",
                        "nationality": "Spain",
                    },
                    {
                        "id": 2,
                        "name": "Jane Smith",
                        "position": "Midfield",
                        "dateOfBirth": "1998-03-20",
                        "nationality": "Brazil",
                    },
                ]
            }

        elif "/matches" in endpoint:
            return {
                "matches": [
                    {
                        "id": 12345,
                        "utcDate": "2025-01-15T15:00:00Z",
                        "status": "FINISHED",
                        "matchday": 20,
                        "stage": "REGULAR_SEASON",
                        "group": None,
                        "homeTeam": {
                            "id": 86,
                            "name": "Mock Team A",
                            "shortName": "Team A",
                            "tla": "MTA",
                            "crest": None,
                        },
                        "awayTeam": {
                            "id": 87,
                            "name": "Mock Team B",
                            "shortName": "Team B",
                            "tla": "MTB",
                            "crest": None,
                        },
                        "score": {
                            "winner": "HOME_TEAM",
                            "duration": "REGULAR",
                            "fullTime": {"home": 2, "away": 1},
                            "halfTime": {"home": 1, "away": 0},
                        },
                        "competition": {
                            "id": 2021,
                            "name": "Premier League",
                            "code": "PL",
                            "type": "LEAGUE",
                            "emblem": None,
                        },
                    },
                ]
            }

        return {}

    async def _get_competitions(self) -> List[Dict[str, Any]]:
        """
        Get list of available competitions.
        Caches results to avoid repeated API calls.

        Returns:
            List of competition data
        """
        if self._competitions_cache:
            return self._competitions_cache

        try:
            data = await self._make_request("GET", "/competitions")
            competitions = data.get("competitions", [])
            self._competitions_cache = competitions
            return competitions
        except Exception:
            return []

    async def _build_team_cache_from_competitions(self) -> None:
        """
        Build team cache by fetching teams from major competitions.
        Football-Data.org doesn't have a team search endpoint, so we search through competitions.
        """
        if self._team_cache:
            return  # Cache already built

        # Major competition codes to search through
        major_competitions = [
            "PL",   # Premier League
            "PD",   # La Liga
            "BL1",  # Bundesliga
            "SA",   # Serie A
            "FL1",  # Ligue 1
            "CL",   # Champions League
        ]

        competitions = await self._get_competitions()

        for competition in competitions:
            comp_code = competition.get("code")
            comp_id = competition.get("id")

            if comp_code not in major_competitions:
                continue

            try:
                # Get teams in this competition
                data = await self._make_request(
                    "GET",
                    f"/competitions/{comp_code}/teams"
                )

                teams = data.get("teams", [])

                for team in teams:
                    team_id = team.get("id")
                    team_name = team.get("name")
                    short_name = team.get("shortName")
                    tla = team.get("tla")

                    if team_id and team_name:
                        # Store team info with normalized name for matching
                        team_info = {
                            "id": str(team_id),
                            "name": team_name,
                            "shortName": short_name,
                            "tla": tla,
                            "competition": competition.get("name"),
                            "competition_code": comp_code,
                        }

                        # Store under multiple keys for better matching
                        self._team_cache[team_name.lower()] = team_info
                        if short_name:
                            self._team_cache[short_name.lower()] = team_info
                        if tla:
                            self._team_cache[tla.lower()] = team_info

            except Exception:
                # Continue if a competition fails
                continue

    def _find_best_team_match(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Find the best matching team from cache using fuzzy matching.

        Args:
            query: Team name to search for

        Returns:
            Team info dict or None if no good match found
        """
        query_lower = query.lower()

        # First try exact match
        if query_lower in self._team_cache:
            return self._team_cache[query_lower]

        # Try fuzzy matching
        best_match = None
        best_ratio = 0.0

        for team_name, team_info in self._team_cache.items():
            # Calculate similarity ratio
            ratio = SequenceMatcher(None, query_lower, team_name).ratio()

            # Also check if query is contained in team name
            if query_lower in team_name:
                ratio = max(ratio, 0.8)  # Boost score for substring matches

            if ratio > best_ratio and ratio > 0.6:  # Threshold for matching
                best_ratio = ratio
                best_match = team_info

        return best_match

    async def search_teams(self, query: str) -> List[TeamSearchResult]:
        """
        Search for teams by name.

        Note: FBRApi doesn't have a native team search endpoint. We try to use
        league standings, but fall back to a static database if the API is unavailable.

        Args:
            query: Search query (team name)

        Returns:
            List of matching teams
        """
        if self.mock_mode:
            data = await self._make_request("GET", "/teams/search", params={"query": query})
            teams_data = data.get("teams", [])
            return [TeamSearchResult(**team) for team in teams_data]

        # Try to build team cache from API
        try:
            await self._build_team_cache_from_leagues()
        except Exception:
            # API failed, use static database fallback
            print("[INFO] FBRApi unavailable, using static team database")

        # If cache is empty, use static database
        if not self._team_cache:
            static_matches = get_all_teams_matching(query)
            return [
                TeamSearchResult(
                    id=team["id"],
                    name=team["name"],
                    country=team.get("country"),
                    league=team.get("league"),
                )
                for team in static_matches[:10]
            ]

        # Find matching teams from cache
        results = []
        query_lower = query.lower()

        for team_name, team_info in self._team_cache.items():
            # Match if query is in team name
            if query_lower in team_name or SequenceMatcher(None, query_lower, team_name).ratio() > 0.6:
                results.append(TeamSearchResult(
                    id=team_info["id"],
                    name=team_info["name"],
                    league=f"League {team_info['league_id']}",
                ))

        return results[:10]  # Limit to top 10 results

    async def get_team(self, team_id: str) -> TeamDetails:
        """
        Get detailed information about a specific team.

        Args:
            team_id: Team ID

        Returns:
            Detailed team information
        """
        data = await self._make_request("GET", f"/teams/{team_id}")
        return TeamDetails(**data)

    async def search_games(self, filters: GameFilters) -> List[GameSearchResult]:
        """
        Search for games based on filters.

        Note: FBRApi uses /matches endpoint (not /games/search) and requires team_id.
        If team_name is provided, we first resolve it to a team_id.

        Args:
            filters: Game search filters

        Returns:
            List of matching games
        """
        if self.mock_mode:
            params = {}
            if filters.team_id:
                params["team_id"] = filters.team_id
            if filters.team_name:
                params["team_name"] = filters.team_name
            if filters.date_from:
                params["date_from"] = filters.date_from
            if filters.date_to:
                params["date_to"] = filters.date_to
            if filters.competition:
                params["competition"] = filters.competition
            data = await self._make_request("GET", "/games/search", params=params)
            games_data = data.get("games", [])
            return [GameSearchResult(**game) for game in games_data]

        # Resolve team_name to team_id if needed
        team_id = filters.team_id
        team_match = None

        if not team_id and filters.team_name:
            # Try to build team cache from API
            try:
                await self._build_team_cache_from_leagues()
                team_match = self._find_best_team_match(filters.team_name)
            except Exception:
                pass

            # If API failed or no match, try static database
            if not team_match:
                print("[INFO] Using static team database for team search")
                team_match = find_team_by_name(filters.team_name)

            if team_match:
                team_id = team_match["id"]
            else:
                # No matching team found
                print(f"[WARNING] No team found matching '{filters.team_name}'")
                return []

        if not team_id:
            raise Exception("Either team_id or team_name must be provided to search for matches")

        # Build params for /teams endpoint to get team_schedule
        # According to FBRApi docs, /teams returns both roster and schedule
        # Don't specify season_id - API will return most recent season by default
        params = {"team_id": team_id}

        # Fetch team data from FBRApi (includes team_schedule)
        data = await self._make_request("GET", "/teams/", params=params)

        # Parse response - extract team_schedule
        matches_data = data.get("team_schedule", {}).get("data", [])

        # Convert to GameSearchResult format and filter by dates
        results = []
        for match in matches_data:
            match_date = match.get("date", "")

            # Filter by date range if provided
            if filters.date_from and match_date < filters.date_from:
                continue
            if filters.date_to and match_date > filters.date_to:
                continue

            # Determine home/away teams
            is_home = match.get("home_away") == "Home"
            team_name = team_match["name"] if team_match else f"Team {team_id}"
            opponent = match.get("opponent", "Unknown")

            results.append(GameSearchResult(
                id=match.get("match_id", ""),
                home_team=team_name if is_home else opponent,
                away_team=opponent if is_home else team_name,
                home_team_id=team_id if is_home else match.get("opponent_id", ""),
                away_team_id=match.get("opponent_id", "") if is_home else team_id,
                date=match_date,
                competition=match.get("league_name", filters.competition),
                status="finished" if match.get("result") else "unknown",
            ))

        return results

    async def get_game(self, game_id: str) -> GameDetails:
        """
        Get detailed information about a specific game.

        Args:
            game_id: Game ID

        Returns:
            Detailed game information including lineups
        """
        data = await self._make_request("GET", f"/games/{game_id}")
        return GameDetails(**data)

    async def get_roster(self, team_id: str) -> List[RosterPlayer]:
        """
        Get roster for a specific team.

        Args:
            team_id: Team ID

        Returns:
            List of players in the team roster
        """
        data = await self._make_request("GET", f"/rosters/{team_id}")

        players_data = data.get("players", [])
        return [RosterPlayer(**player) for player in players_data]
