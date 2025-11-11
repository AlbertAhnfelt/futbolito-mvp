import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
# Navigate up from backend/src/video_analysis/ to project root
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

# Get API keys from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# DEBUG MODE: Set to "true" to skip TTS and video generation (commentary text only)
# This is useful for testing the graph LLM without using ElevenLabs credits
# To enable: Add DEBUG_COMMENTARY_ONLY=true to your .env file
# TO REMOVE THIS FEATURE LATER: Search for "DEBUG_COMMENTARY_ONLY" across the codebase
_debug_value = os.getenv("DEBUG_COMMENTARY_ONLY", "false")
DEBUG_COMMENTARY_ONLY = _debug_value.strip().lower() == "true"

# Print debug mode status on module load
if DEBUG_COMMENTARY_ONLY:
    print(f"\n{'='*60}")
    print(f"🔧 DEBUG MODE ENABLED: Commentary-Only Mode Active")
    print(f"{'='*60}\n")

