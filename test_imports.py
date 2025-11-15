"""
Simple test script to validate imports work correctly.
This doesn't run the actual pipeline, just checks that all modules can be imported.
"""

import sys
from pathlib import Path

# Add backend/src to path
backend_src = Path(__file__).parent / 'backend' / 'src'
sys.path.insert(0, str(backend_src))

print("Testing imports...")
print("=" * 60)

try:
    print("1. Importing video_analysis package...")
    from video_analysis import GEMINI_API_KEY, ELEVENLABS_API_KEY
    print("   [OK] Main package imported")
    print(f"   [OK] GEMINI_API_KEY: {'Set' if GEMINI_API_KEY else 'Not set'}")
    print(f"   [OK] ELEVENLABS_API_KEY: {'Set' if ELEVENLABS_API_KEY else 'Not set'}")

    print("\n2. Importing analysis module...")
    from video_analysis.analysis.event_detector import EventDetector
    from video_analysis.analysis.models import Event, EventsOutput
    print("   [OK] EventDetector imported")
    print("   [OK] Event models imported")

    print("\n3. Importing commentary module...")
    from video_analysis.commentary.commentary_generator import CommentaryGenerator
    from video_analysis.commentary.models import Commentary, CommentaryOutput
    print("   [OK] CommentaryGenerator imported")
    print("   [OK] Commentary models imported")

    print("\n4. Importing video module...")
    from video_analysis.video.video_processor import VideoProcessor
    from video_analysis.video.time_utils import parse_time_to_seconds, seconds_to_time
    print("   [OK] VideoProcessor imported")
    print("   [OK] Time utilities imported")

    print("\n5. Importing controller...")
    from video_analysis.controller import analyze_video, list_videos
    print("   [OK] Controller functions imported")

    print("\n6. Importing audio module...")
    from video_analysis.audio.tts_generator import TTSGenerator
    print("   [OK] TTSGenerator imported")

    print("\n7. Importing context manager...")
    from video_analysis.context_manager import ContextManager, get_context_manager
    print("   [OK] ContextManager imported")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL IMPORTS SUCCESSFUL!")
    print("=" * 60)

    # Test time utilities
    print("\n8. Testing time utilities...")
    test_time = seconds_to_time(5445)
    print(f"   seconds_to_time(5445) = {test_time}")
    test_seconds = parse_time_to_seconds("01:30:45")
    print(f"   parse_time_to_seconds('01:30:45') = {test_seconds}")
    assert test_time == "01:30:45", "Time conversion mismatch!"
    assert test_seconds == 5445.0, "Time parsing mismatch!"
    print("   [OK] Time utilities working correctly")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL TESTS PASSED!")
    print("=" * 60)

except Exception as e:
    print("\n" + "=" * 60)
    print("[ERROR] IMPORT TEST FAILED!")
    print("=" * 60)
    print(f"Error: {e}")
    import traceback
    print(traceback.format_exc())
    sys.exit(1)
