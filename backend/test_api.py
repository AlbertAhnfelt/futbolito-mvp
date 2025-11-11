"""Test script for FBRApi client."""
import asyncio
import sys
import os
from pathlib import Path

# Load .env file from project root
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

sys.path.insert(0, 'src')

from football_api.client import FBRApiClient

async def main():
    client = FBRApiClient()

    print("=" * 60)
    print("Testing FBRApi Client")
    print("=" * 60)

    # Test 1: Team search
    print("\n1. Testing team search...")
    try:
        teams = await client.search_teams("Manchester United")
        print(f"   [OK] Found {len(teams)} teams:")
        for team in teams:
            print(f"     - {team.name} (ID: {team.id})")
    except Exception as e:
        print(f"   [ERROR] Error searching teams: {e}")

    # Test 2: Game search
    print("\n2. Testing game search...")
    try:
        from football_api.models import GameFilters
        filters = GameFilters(team_name="Manchester United")
        games = await client.search_games(filters)
        print(f"   [OK] Found {len(games)} games for Manchester United")
        if games:
            print(f"     Latest match: {games[0].home_team} vs {games[0].away_team} on {games[0].date}")
    except Exception as e:
        print(f"   [ERROR] Error searching games: {e}")

    print("\n" + "=" * 60)
    print("Tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
