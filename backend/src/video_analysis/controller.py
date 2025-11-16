import json
import time
import traceback
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types

from . import GEMINI_API_KEY, ELEVENLABS_API_KEY
from .audio.tts_generator import TTSGenerator
from .analysis.event_detector import EventDetector
from .commentary.commentary_generator import CommentaryGenerator
from .video.video_processor import VideoProcessor
from .video.time_utils import parse_time_to_seconds


def list_videos():
    """List all MP4 files in the videos directory."""
    videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
    videos_dir.mkdir(exist_ok=True)

    # Get all MP4 files
    video_files = [f.name for f in videos_dir.glob('*.mp4')]
    return video_files


async def analyze_video(filename: str):
    """
    Analyze a video file using the new two-process pipeline:
    1. Event detection (30-second intervals)
    2. Commentary generation (from detected events)
    3. TTS audio generation
    4. Video generation with commentary overlay (1-second delay)
    """
    try:
        print(f"\n{'='*60}")
        print(f"🎬 VIDEO ANALYSIS PIPELINE - NEW SYSTEM")
        print(f"{'='*60}\n")

        # Initialize Gemini client
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Get video path
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
        video_path = videos_dir / filename

        if not video_path.exists():
            raise FileNotFoundError(f"Video file {filename} not found")

        # Initialize video processor
        video_processor = VideoProcessor()

        # Ensure video has audio (add silent audio if needed)
        print("Step 1: Preparing video...")
        video_path_with_audio = video_processor.ensure_video_has_audio(video_path)

        # Get video duration
        video_duration = video_processor.get_video_duration(video_path_with_audio)

        # Upload video to Gemini File API
        print(f"\nStep 2: Uploading video to Gemini...")
        print(f"Video: {video_path_with_audio}")
        uploaded_file = client.files.upload(file=str(video_path_with_audio))
        file_name = uploaded_file.name

        # Wait for file to be processed and become ACTIVE
        print(f"Uploaded file: {file_name}")
        print(f"Waiting for processing...")
        max_retries = 60  # Wait up to 60 seconds
        retry_count = 0

        while retry_count < max_retries:
            file_info = client.files.get(name=file_name)

            if file_info.state.name == "ACTIVE":
                print(f"✓ File is ready for analysis!")
                break

            print(f"  File state: {file_info.state.name}. Waiting...")
            time.sleep(1)
            retry_count += 1

        if retry_count == max_retries:
            raise TimeoutError("File processing timeout")

        file_uri = uploaded_file.uri

        # ============================================================
        # PROCESS 1: EVENT DETECTION (30-second intervals)
        # ============================================================
        print(f"\nStep 3: Event Detection")
        print(f"Analyzing video in 30-second intervals...")

        event_detector = EventDetector(api_key=GEMINI_API_KEY)
        events = event_detector.detect_events(
            file_uri=file_uri,
            duration_seconds=video_duration,
            interval_seconds=30
        )

        print(f"\n✓ Event detection completed!")
        print(f"  Total events detected: {len(events)}")
        print(f"  Events saved to: output/events.json")

        # ============================================================
        # PROCESS 2: COMMENTARY GENERATION (from events)
        # ============================================================
        print(f"\nStep 4: Commentary Generation")
        print(f"Generating commentary from detected events...")

        commentary_generator = CommentaryGenerator(api_key=GEMINI_API_KEY)

        # Convert events to dict format for commentary generator
        events_dict = [e.model_dump() for e in events]

        commentaries = commentary_generator.generate_commentary(
            events=events_dict,
            video_duration=video_duration,
            use_streaming=False  # TODO: Implement streaming in future
        )

        print(f"\n✓ Commentary generation completed!")
        print(f"  Total commentary segments: {len(commentaries)}")
        print(f"  Commentaries saved to: output/commentary.json")

        # ============================================================
        # STEP 3: TTS AUDIO GENERATION
        # ============================================================
        print(f"\nStep 5: TTS Audio Generation")
        print(f"Generating audio for {len(commentaries)} commentary segments...")

        commentaries_dict = []

        if ELEVENLABS_API_KEY:
            try:
                tts_generator = TTSGenerator(
                    api_key=ELEVENLABS_API_KEY,
                    default_voice_id="nrD2uNU2IUYtedZegcGx"
                )

                for i, commentary in enumerate(commentaries):
                    print(f"  [{i+1}/{len(commentaries)}] Generating audio...")
                    print(f"    Text: {commentary.commentary[:80]}...")

                    audio_base64 = tts_generator.generate_audio(commentary.commentary)

                    commentary_dict = commentary.model_dump()
                    if audio_base64:
                        print(f"    ✓ Audio generated ({len(audio_base64)} chars)")
                        commentary_dict['audio_base64'] = audio_base64
                    else:
                        print(f"    ✗ TTS returned empty audio")
                        commentary_dict['audio_base64'] = ""

                    commentaries_dict.append(commentary_dict)

                print(f"\n✓ TTS audio generation completed!")

            except Exception as e:
                print(f"[ERROR] TTS generation failed: {str(e)}")
                print(traceback.format_exc())
                # Add empty audio to all commentaries
                for commentary in commentaries:
                    commentary_dict = commentary.model_dump()
                    commentary_dict['audio_base64'] = ""
                    commentaries_dict.append(commentary_dict)
        else:
            print("[WARN] ELEVENLABS_API_KEY not found, skipping TTS generation")
            for commentary in commentaries:
                commentary_dict = commentary.model_dump()
                commentary_dict['audio_base64'] = ""
                commentaries_dict.append(commentary_dict)

        # ============================================================
        # STEP 4: VIDEO GENERATION (with 1-second audio delay)
        # ============================================================
        print(f"\nStep 6: Video Generation")
        print(f"Creating video with commentary overlay...")
        print(f"IMPORTANT: Audio will be delayed by 1 second from start_time")

        output_filename = video_processor.generate_commentary_video(
            video_path=video_path,
            commentaries=commentaries_dict
        )

        print(f"\n{'='*60}")
        print(f"✓ VIDEO ANALYSIS COMPLETED SUCCESSFULLY!")
        print(f"{'='*60}")
        print(f"Events detected: {len(events)}")
        print(f"Commentary segments: {len(commentaries)}")
        print(f"Generated video: {output_filename}")
        print(f"{'='*60}\n")

        # Create highlights for frontend (commentary segments only)
        highlights = []
        for commentary_dict in commentaries_dict:
            # Find events within this commentary's time range for intensity calculation
            start_secs = parse_time_to_seconds(commentary_dict['start_time'])
            end_secs = parse_time_to_seconds(commentary_dict['end_time'])

            # Get events in this time range
            events_in_range = [
                e for e in events
                if start_secs <= parse_time_to_seconds(e.time) <= end_secs
            ]

            # Calculate average intensity from events
            if events_in_range:
                avg_intensity = sum(e.intensity for e in events_in_range) / len(events_in_range)
            else:
                avg_intensity = 5

            highlight = {
                'start_time': commentary_dict['start_time'],
                'end_time': commentary_dict['end_time'],
                'commentary': commentary_dict['commentary'],
                'intensity': int(avg_intensity)
            }

            # Add audio_base64 if present
            if 'audio_base64' in commentary_dict:
                highlight['audio_base64'] = commentary_dict['audio_base64']

            highlights.append(highlight)

        # Return results
        return {
            'events': [e.model_dump() for e in events],
            'commentaries': [c.model_dump() for c in commentaries],
            'highlights': highlights,  # For frontend compatibility
            'generated_video': output_filename
        }

    except Exception as e:
        print("=" * 60)
        print("ERROR in analyze_video:")
        print(traceback.format_exc())
        print("=" * 60)
        raise

