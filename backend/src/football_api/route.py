"""
FastAPI routes for football API endpoints.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from .service import get_football_service
from .models import (
    TeamSearchResult,
    TeamDetails,
    GameSearchResult,
    GameDetails,
    GameFilters,
    RosterPlayer,
)

router = APIRouter(prefix="/api", tags=["football"])


@router.get("/teams/search", response_model=List[TeamSearchResult])
async def search_teams(
    query: str = Query(..., min_length=2, description="Team name search query")
):
    """
    Search for teams by name.

    Args:
        query: Search query (minimum 2 characters)

    Returns:
        List of matching teams
    """
    try:
        service = get_football_service()
        teams = await service.search_teams(query)
        return teams
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search teams: {str(e)}")


@router.get("/teams/{team_id}", response_model=TeamDetails)
async def get_team(team_id: str):
    """
    Get detailed information about a specific team.

    Args:
        team_id: Team ID

    Returns:
        Detailed team information including roster
    """
    try:
        service = get_football_service()
        team = await service.get_team(team_id)
        return team
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team: {str(e)}")


@router.get("/games/search", response_model=List[GameSearchResult])
async def search_games(
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    team_name: Optional[str] = Query(None, description="Filter by team name"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    competition: Optional[str] = Query(None, description="Filter by competition name"),
):
    """
    Search for games based on filters.

    Args:
        team_id: Filter by team ID
        team_name: Filter by team name
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
        competition: Filter by competition name

    Returns:
        List of matching games
    """
    try:
        filters = GameFilters(
            team_id=team_id,
            team_name=team_name,
            date_from=date_from,
            date_to=date_to,
            competition=competition,
        )

        service = get_football_service()
        games = await service.search_games(filters)
        return games
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search games: {str(e)}")


@router.get("/games/{game_id}", response_model=GameDetails)
async def get_game(game_id: str):
    """
    Get detailed information about a specific game.

    Args:
        game_id: Game ID

    Returns:
        Detailed game information including lineups
    """
    try:
        service = get_football_service()
        game = await service.get_game(game_id)
        return game
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get game: {str(e)}")


@router.get("/rosters/{team_id}", response_model=List[RosterPlayer])
async def get_roster(team_id: str):
    """
    Get roster for a specific team.

    Args:
        team_id: Team ID

    Returns:
        List of players in the team roster
    """
    try:
        service = get_football_service()
        roster = await service.get_roster(team_id)
        return roster
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get roster: {str(e)}")


@router.delete("/cache")
async def clear_cache(
    cache_type: Optional[str] = Query(None, description="Type of cache to clear: 'teams', 'games', 'rosters', or leave empty for all")
):
    """
    Clear API response cache.

    Args:
        cache_type: Type of cache to clear ('teams', 'games', 'rosters', or None for all)

    Returns:
        Success message
    """
    try:
        service = get_football_service()
        service.clear_cache(cache_type)
        cache_msg = cache_type if cache_type else "all"
        return {"message": f"Successfully cleared {cache_msg} cache"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
