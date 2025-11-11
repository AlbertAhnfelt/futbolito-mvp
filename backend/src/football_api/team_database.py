"""
Static team database for fallback when FBRApi is unavailable.
Contains major teams from top European leagues.
"""

# Static team database: team_name_lower -> team_info
TEAM_DATABASE = {
    # Premier League
    "manchester united": {
        "id": "19538871",
        "name": "Manchester Utd",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    "manchester city": {
        "id": "b8fd03ef",
        "name": "Manchester City",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    "liverpool": {
        "id": "822bd0ba",
        "name": "Liverpool",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    "chelsea": {
        "id": "cff3d9bb",
        "name": "Chelsea",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    "arsenal": {
        "id": "18bb7c10",
        "name": "Arsenal",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    "tottenham": {
        "id": "361ca564",
        "name": "Tottenham",
        "country": "England",
        "league": "Premier League",
        "league_id": 9,
    },
    # La Liga
    "real madrid": {
        "id": "53a2f082",
        "name": "Real Madrid",
        "country": "Spain",
        "league": "La Liga",
        "league_id": 12,
    },
    "barcelona": {
        "id": "206d90db",
        "name": "Barcelona",
        "country": "Spain",
        "league": "La Liga",
        "league_id": 12,
    },
    "atletico madrid": {
        "id": "db3b9613",
        "name": "Atlético Madrid",
        "country": "Spain",
        "league": "La Liga",
        "league_id": 12,
    },
    # Bundesliga
    "bayern munich": {
        "id": "054efa67",
        "name": "Bayern Munich",
        "country": "Germany",
        "league": "Bundesliga",
        "league_id": 20,
    },
    "borussia dortmund": {
        "id": "add600ae",
        "name": "Dortmund",
        "country": "Germany",
        "league": "Bundesliga",
        "league_id": 20,
    },
    # Serie A
    "juventus": {
        "id": "e0652b02",
        "name": "Juventus",
        "country": "Italy",
        "league": "Serie A",
        "league_id": 11,
    },
    "inter milan": {
        "id": "05ac8dcf",
        "name": "Inter",
        "country": "Italy",
        "league": "Serie A",
        "league_id": 11,
    },
    "ac milan": {
        "id": "03c3cd7e",
        "name": "Milan",
        "country": "Italy",
        "league": "Serie A",
        "league_id": 11,
    },
    # Ligue 1
    "psg": {
        "id": "e2d8892c",
        "name": "Paris S-G",
        "country": "France",
        "league": "Ligue 1",
        "league_id": 13,
    },
    "paris saint-germain": {
        "id": "e2d8892c",
        "name": "Paris S-G",
        "country": "France",
        "league": "Ligue 1",
        "league_id": 13,
    },
}


def find_team_by_name(query: str) -> dict:
    """
    Find team info by name using fuzzy matching.

    Args:
        query: Team name to search for

    Returns:
        Team info dict or None if not found
    """
    from difflib import SequenceMatcher

    query_lower = query.lower()

    # Exact match
    if query_lower in TEAM_DATABASE:
        return TEAM_DATABASE[query_lower]

    # Partial match
    for team_name, team_info in TEAM_DATABASE.items():
        if query_lower in team_name or team_name in query_lower:
            return team_info

    # Fuzzy match
    best_match = None
    best_ratio = 0.0

    for team_name, team_info in TEAM_DATABASE.items():
        ratio = SequenceMatcher(None, query_lower, team_name).ratio()
        if ratio > best_ratio and ratio > 0.6:
            best_ratio = ratio
            best_match = team_info

    return best_match


def get_all_teams_matching(query: str) -> list:
    """
    Get all teams matching the query.

    Args:
        query: Team name to search for

    Returns:
        List of team info dicts
    """
    from difflib import SequenceMatcher

    query_lower = query.lower()
    matches = []

    for team_name, team_info in TEAM_DATABASE.items():
        # Check if query matches
        if (query_lower in team_name or
            team_name in query_lower or
            SequenceMatcher(None, query_lower, team_name).ratio() > 0.6):
            matches.append(team_info)

    return matches
