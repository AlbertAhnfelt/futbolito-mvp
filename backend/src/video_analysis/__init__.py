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



