import json
import asyncio
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

class StateManager:
    """
    Manages the shared state between Event Detection (Producer) and
    Commentary Generation (Consumer). Handles file I/O with async locks.

    This is the PRIMARY state management system for the entire pipeline.
    All state updates must go through StateManager to ensure consistency.
    """
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize StateManager with proper output directory.

        Args:
            output_dir: Directory to store events.json and commentary.json
                       If None, defaults to ./output
        """
        # Async lock to prevent race conditions when reading/writing JSONs
        self.lock = asyncio.Lock()

        # Logic Variable: Tracks how many seconds of the match have been analyzed
        self._time_analyzed = 0.0

        # Data stores (in-memory cache)
        self.events = []
        self.commentary = []

        # Set up file paths
        if output_dir is None:
            output_dir = Path("output")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

        self.EVENTS_FILE = self.output_dir / "events.json"
        self.COMMENTARY_FILE = self.output_dir / "commentary.json"

        print(f"[STATE MANAGER] Initialized with output_dir: {self.output_dir.absolute()}")
        print(f"[STATE MANAGER] Events file: {self.EVENTS_FILE}")
        print(f"[STATE MANAGER] Commentary file: {self.COMMENTARY_FILE}")

    async def init_files(self):
        """
        Initialize JSON files. Loads existing data if present, creates new files if not.
        This should be called after __init__ and is async-safe.
        """
        async with self.lock:
            # Load existing events if file exists, otherwise create empty
            if self.EVENTS_FILE.exists():
                try:
                    with open(self.EVENTS_FILE, 'r') as f:
                        data = json.load(f)
                        # Handle both {"events": [...]} and [...] formats
                        if isinstance(data, dict) and "events" in data:
                            self.events = data["events"]
                        elif isinstance(data, list):
                            self.events = data
                        else:
                            self.events = []
                    print(f"[STATE MANAGER] Loaded {len(self.events)} existing events")
                except Exception as e:
                    print(f"[STATE MANAGER] Error loading events.json: {e}, starting fresh")
                    self.events = []
                    with open(self.EVENTS_FILE, 'w') as f:
                        json.dump({"events": []}, f, indent=2)
            else:
                self.events = []
                with open(self.EVENTS_FILE, 'w') as f:
                    json.dump({"events": []}, f, indent=2)

            # Load existing commentary if file exists, otherwise create empty
            if self.COMMENTARY_FILE.exists():
                try:
                    with open(self.COMMENTARY_FILE, 'r') as f:
                        data = json.load(f)
                        # Handle both {"commentaries": [...]} and [...] formats
                        if isinstance(data, dict) and "commentaries" in data:
                            self.commentary = data["commentaries"]
                        elif isinstance(data, list):
                            self.commentary = data
                        else:
                            self.commentary = []
                    print(f"[STATE MANAGER] Loaded {len(self.commentary)} existing commentaries")
                except Exception as e:
                    print(f"[STATE MANAGER] Error loading commentary.json: {e}, starting fresh")
                    self.commentary = []
                    with open(self.COMMENTARY_FILE, 'w') as f:
                        json.dump({"commentaries": []}, f, indent=2)
            else:
                self.commentary = []
                with open(self.COMMENTARY_FILE, 'w') as f:
                    json.dump({"commentaries": []}, f, indent=2)

    # --- TIME ANALYZED MANAGEMENT (Logic A, B, D) ---

    async def update_time_analyzed(self, new_time: float):
        """
        Called by Logic A & B after analyzing a video chunk.

        Args:
            new_time: Time in seconds that has been analyzed
        """
        async with self.lock:
            self._time_analyzed = new_time
            print(f"[STATE MANAGER] Time analyzed updated to: {self._time_analyzed}s")

    async def get_time_analyzed(self) -> float:
        """
        Called by Logic D to check if it can proceed.

        Returns:
            Time in seconds that has been analyzed
        """
        async with self.lock:
            return self._time_analyzed

    # --- EVENT MANAGEMENT (Logic A & B) ---

    async def add_events(self, new_events: List[Dict[str, Any]]):
        """
        Adds new events found by Gemini to the list and saves to file.
        This is the PRIMARY method for adding events to the system.

        Args:
            new_events: List of event dictionaries to add
        """
        async with self.lock:
            self.events.extend(new_events)
            await self._save_events_to_file()
            print(f"[STATE MANAGER] Added {len(new_events)} new events (total: {len(self.events)})")

    async def get_events_up_to(self, time_str: str) -> List[Dict[str, Any]]:
        """
        Retrieves events that happened before a certain time.
        Used by Logic C & D to generate commentary context.

        Args:
            time_str: Time in HH:MM:SS format

        Returns:
            List of event dictionaries
        """
        from .video.time_utils import parse_time_to_seconds

        async with self.lock:
            target_seconds = parse_time_to_seconds(time_str)
            # Events use 'time' field in HH:MM:SS format
            return [
                e for e in self.events
                if parse_time_to_seconds(e.get('time', '00:00:00')) <= target_seconds
            ]

    async def get_all_events(self) -> List[Dict[str, Any]]:
        """
        Get all events in the system.

        Returns:
            List of all event dictionaries
        """
        async with self.lock:
            return self.events.copy()

    # --- COMMENTARY MANAGEMENT (Logic C & D) ---

    async def add_commentaries(self, new_commentaries: List[Dict[str, Any]]):
        """
        Adds generated commentary segments and saves to file.
        This is the PRIMARY method for adding commentaries to the system.

        Args:
            new_commentaries: List of commentary dictionaries to add
        """
        async with self.lock:
            self.commentary.extend(new_commentaries)
            await self._save_commentaries_to_file()
            print(f"[STATE MANAGER] Added {len(new_commentaries)} new commentaries (total: {len(self.commentary)})")

    async def add_commentary(self, commentary_entry: Dict[str, Any]):
        """
        Adds a single generated commentary segment and saves to file.

        Args:
            commentary_entry: Commentary dictionary with start_time, end_time, commentary fields
        """
        await self.add_commentaries([commentary_entry])

    async def get_last_commentary_end_time(self) -> str:
        """
        Used by Logic D to calculate where the next segment starts.

        Returns:
            End time of last commentary in HH:MM:SS format, or "00:00:00" if no commentary
        """
        async with self.lock:
            if not self.commentary:
                return "00:00:00"
            return self.commentary[-1].get('end_time', '00:00:00')

    async def get_all_commentaries(self) -> List[Dict[str, Any]]:
        """
        Get all commentaries in the system.

        Returns:
            List of all commentary dictionaries
        """
        async with self.lock:
            return self.commentary.copy()

    # --- FILE I/O UTILS ---

    async def _save_events_to_file(self):
        """Save events to events.json (must be called within lock)."""
        try:
            with open(self.EVENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"events": self.events}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE MANAGER ERROR] Failed to save events.json: {e}")

    async def _save_commentaries_to_file(self):
        """Save commentaries to commentary.json (must be called within lock)."""
        try:
            with open(self.COMMENTARY_FILE, 'w', encoding='utf-8') as f:
                json.dump({"commentaries": self.commentary}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[STATE MANAGER ERROR] Failed to save commentary.json: {e}")