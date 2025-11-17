"""
Match Context Manager for RAG/Knowledge Base.

Handles loading, saving, and formatting of match context (team names, player info)
for use in commentary generation.
"""

import json
from pathlib import Path
from typing import Optional, Dict, List
from pydantic import BaseModel


class Player(BaseModel):
    """Player information."""
    jersey: str
    name: str
    position: Optional[str] = None
    notes: Optional[str] = None


class Team(BaseModel):
    """Team information."""
    name: str
    shirt_color: Optional[str] = None
    players: List[Player] = []


class MatchContext(BaseModel):
    """Match context containing team and player information."""
    teams: Dict[str, Team]


class ContextManager:
    """
    Manages match context for commentary generation.

    Provides fast loading, saving, and formatting of player/team data
    to inject into LLM prompts.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize context manager.

        Args:
            data_dir: Directory for storing match context data.
                     Defaults to backend/data/
        """
        if data_dir is None:
            # Default to backend/data/ directory
            data_dir = Path(__file__).parent.parent.parent.parent / 'data'

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.context_file = self.data_dir / 'match_context.json'

        # In-memory cache for fast access
        self._cache: Optional[MatchContext] = None

    def save_context(self, context: MatchContext) -> None:
        """
        Save match context to file and update cache.

        Args:
            context: Match context to save
        """
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(context.model_dump(), f, indent=2, ensure_ascii=False)

        # Update cache
        self._cache = context
        print(f"[CONTEXT] Saved match context to {self.context_file}")

    def load_context(self) -> Optional[MatchContext]:
        """
        Load match context from file (uses cache if available).

        Returns:
            MatchContext if exists, None otherwise
        """
        # Return cached version if available
        if self._cache is not None:
            return self._cache

        # Load from file
        if not self.context_file.exists():
            print("[CONTEXT] No match context file found")
            return None

        try:
            with open(self.context_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            context = MatchContext(**data)

            # Check if context is empty (no team names set)
            if not context.teams.get('home') or not context.teams['home'].name:
                print("[CONTEXT] Match context is empty")
                return None

            # Cache the loaded context
            self._cache = context
            print(f"[CONTEXT] Loaded match context: {context.teams['home'].name} vs {context.teams['away'].name}")
            return context

        except Exception as e:
            print(f"[CONTEXT] Error loading match context: {e}")
            return None

    def clear_context(self) -> None:
        """Clear match context (reset to empty state)."""
        empty_context = MatchContext(teams={
            'home': Team(name='', shirt_color=None, players=[]),
            'away': Team(name='', shirt_color=None, players=[])
        })
        self.save_context(empty_context)
        self._cache = None
        print("[CONTEXT] Cleared match context")

    def format_for_prompt(self, context: Optional[MatchContext] = None) -> str:
        """
        Format match context as readable text for LLM prompt injection.

        Args:
            context: Match context to format. If None, loads from file.

        Returns:
            Formatted string for prompt injection, or empty string if no context
        """
        if context is None:
            context = self.load_context()

        if context is None:
            return ""

        lines = ["MATCH CONTEXT (Use player names instead of jersey numbers):"]
        lines.append("")

        # Format home team
        home = context.teams.get('home')
        if home and home.name:
            team_header = f"HOME TEAM: {home.name}"
            if home.shirt_color:
                team_header += f" (wearing {home.shirt_color})"
            lines.append(team_header)
            if home.players:
                lines.append("Players:")
                for player in home.players:
                    player_info = f"  - #{player.jersey}: {player.name}"
                    if player.position:
                        player_info += f" ({player.position})"
                    if player.notes:
                        player_info += f" - {player.notes}"
                    lines.append(player_info)
            lines.append("")

        # Format away team
        away = context.teams.get('away')
        if away and away.name:
            team_header = f"AWAY TEAM: {away.name}"
            if away.shirt_color:
                team_header += f" (wearing {away.shirt_color})"
            lines.append(team_header)
            if away.players:
                lines.append("Players:")
                for player in away.players:
                    player_info = f"  - #{player.jersey}: {player.name}"
                    if player.position:
                        player_info += f" ({player.position})"
                    if player.notes:
                        player_info += f" - {player.notes}"
                    lines.append(player_info)
            lines.append("")

        lines.append("IMPORTANT: When you see a player wearing jersey #X, use their actual name from the list above.")
        lines.append("Example: Instead of 'Player 10', say 'Lionel Messi (10)' or just 'Messi'.")
        lines.append("")

        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        """Invalidate the in-memory cache (forces reload on next access)."""
        self._cache = None


# Global instance for convenience
_context_manager = ContextManager()


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    return _context_manager
