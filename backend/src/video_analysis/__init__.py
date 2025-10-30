import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

