import json
import time
import traceback
import base64
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types
from pydantic import BaseModel
from imageio_ffmpeg import get_ffmpeg_exe
from . import GEMINI_API_KEY, ELEVENLABS_API_KEY, DEBUG_COMMENTARY_ONLY
from .audio.tts_generator import TTSGenerator
from .graph_llm.orchestrator import GraphOrchestrator


def ensure_video_has_audio(video_path: Path) -> Path:
    """
    Ensure video has an audio track. If not, add a silent audio track.

    This prevents Gemini API errors when processing muted videos.

    Args:
        video_path: Path to the video file

    Returns:
        Path to video with audio (either original or a temp file with audio added)
    """
    try:
        ffmpeg_exe = get_ffmpeg_exe()

        # Check if video has audio track
        probe_cmd = [
            ffmpeg_exe, '-i', str(video_path),
            '-show_streams', '-select_streams', 'a',
            '-loglevel', 'error'
        ]

        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # If there's no audio stream, add silent audio
        if not result.stdout or 'Stream' not in result.stdout:
            print("WARNING: Video has no audio track. Adding silent audio...")

            # Create a temporary file with audio
            temp_dir = Path(tempfile.gettempdir())
            temp_video = temp_dir / f"video_with_audio_{video_path.stem}.mp4"

            # Add silent audio track
            cmd = [
                ffmpeg_exe, '-y',
                '-i', str(video_path),
                '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',
                str(temp_video)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=False
            )

            if result.returncode != 0:
                print(f"Warning: Failed to add audio track: {result.stderr}")
                return video_path

            print(f"SUCCESS: Silent audio track added: {temp_video}")
            return temp_video
        else:
            print("SUCCESS: Video already has audio track")
            return video_path

    except Exception as e:
        print(f"Warning: Could not check/add audio: {str(e)}")
        return video_path


def parse_time_to_seconds(time_str: str) -> float:
    """Convert time string to seconds. Supports HH:MM:SS, MM:SS, or SS formats."""
    parts = time_str.split(':')

    if len(parts) == 3:
        # HH:MM:SS format
        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
    elif len(parts) == 2:
        # MM:SS format
        m, s = int(parts[0]), float(parts[1])
        return m * 60 + s
    elif len(parts) == 1:
        # SS format (just seconds)
        return float(parts[0])
    else:
        raise ValueError(f"Invalid time format: {time_str}. Expected HH:MM:SS, MM:SS, or SS")


def validate_commentary_duration(highlights: list) -> list:
    """
    Ensure each commentary fits within its specific highlight duration.
    Uses average speech rate of 2.5 words/second (150 words/minute).
    Only modifies 'commentary' field, leaves 'description' untouched.
    """
    WORDS_PER_SECOND = 2.5  # Conservative estimate for clear commentary

    for highlight in highlights:
        # Calculate duration for this specific highlight
        start_seconds = parse_time_to_seconds(highlight['start_time'])
        end_seconds = parse_time_to_seconds(highlight['end_time'])
        duration = end_seconds - start_seconds

        # Calculate max words allowed for this duration
        max_words = int(duration * WORDS_PER_SECOND)

        # Check commentary word count
        commentary_words = highlight['commentary'].split()

        if len(commentary_words) > max_words:
            # Truncate at sentence boundary if possible
            truncated = ' '.join(commentary_words[:max_words])

            # Try to end at last complete sentence
            for punct in ['.', '!', '?']:
                if punct in truncated:
                    truncated = truncated.rsplit(punct, 1)[0] + punct
                    break

            print(f"[WARN] Highlight {highlight['start_time']}-{highlight['end_time']}: "
                  f"Truncated commentary from {len(commentary_words)} to {max_words} words "
                  f"(duration: {duration:.1f}s)")

            highlight['commentary'] = truncated

    return highlights


# Define highlight schema
class Highlight(BaseModel):
    start_time: str
    end_time: str
    description: str
    commentary: str
    audio_base64: Optional[str] = None


# TTS generation is now handled by audio.tts_generator.TTSGenerator
# Initialize TTS generator (will be created per request in analyze_video)


def generate_commentary_video(video_path: Path, highlights: list) -> str:
    """
    Generate a video with commentary audio overlaid at specific timestamps.

    Args:
        video_path: Path to the original video file
        highlights: List of highlights with audio_base64, start_time, end_time

    Returns:
        Filename of the generated video (saved in videos/generated-videos/)
    """
    try:
        # Get bundled FFmpeg executable path
        ffmpeg_exe = get_ffmpeg_exe()
        print(f"Using FFmpeg from: {ffmpeg_exe}")

        # Create output directory
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
        output_dir = videos_dir / 'generated-videos'
        output_dir.mkdir(exist_ok=True)

        # Generate output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"commentary_{timestamp}.mp4"
        output_path = output_dir / output_filename

        # Create temporary directory for audio files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            audio_files = []

            # Save each audio_base64 to temporary MP3 files
            print(f"Saving {len(highlights)} audio files...")
            for i, highlight in enumerate(highlights):
                if not highlight.get('audio_base64'):
                    print(f"Warning: No audio for highlight {i+1}, skipping...")
                    continue

                # Decode base64 audio
                audio_bytes = base64.b64decode(highlight['audio_base64'])

                # Save to temporary file
                audio_file = temp_path / f"audio_{i}.mp3"
                audio_file.write_bytes(audio_bytes)

                # Calculate delay in milliseconds
                start_seconds = parse_time_to_seconds(highlight['start_time'])
                delay_ms = int(start_seconds * 1000)

                audio_files.append({
                    'path': audio_file,
                    'delay_ms': delay_ms,
                    'index': i
                })

            if not audio_files:
                print(f"[WARN]  No valid audio files found!")
                print(f"   Total highlights: {len(highlights)}")
                print(f"   Highlights with audio: 0")
                for i, h in enumerate(highlights):
                    has_audio = "[YES]" if h.get('audio_base64') else "[NO]"
                    print(f"   Highlight {i+1}: {has_audio}")
                print(f"")
                print(f"[INFO]  Generating video without commentary audio...")
                print(f"   TTS generation failed for all segments (likely quota issue).")
                print(f"   The video will be created with original audio only.")
                print(f"   Check your ElevenLabs quota and try again when credits are available.")
                print(f"")

                # Instead of raising error, create video with original audio only
                # Just copy the original video as the output
                import shutil
                output_path = video_path.parent / f"{video_path.stem}_commented.mp4"
                shutil.copy(video_path, output_path)

                print(f"[OK] Video saved (original audio only): {output_path.name}")
                return output_path.name

            # Build ffmpeg command using bundled executable
            # Strategy: delay each audio and mix all together, allowing overlaps
            print("Building ffmpeg command...")
            cmd = [ffmpeg_exe, '-y', '-i', str(video_path)]

            # Add all audio inputs
            for audio_info in audio_files:
                cmd.extend(['-i', str(audio_info['path'])])

            # Build filter_complex
            # Delay each audio input and then mix all together
            filter_parts = []

            # Reduce original video audio to 20% volume
            filter_parts.append(f"[0:a]volume=0.2[orig]")

            for i, audio_info in enumerate(audio_files):
                delay_ms = audio_info['delay_ms']
                # Audio input index starts at 1 (0 is video)
                audio_input_idx = i + 1
                label = f"a{i}"
                # Add delay filter (adelay uses milliseconds and needs to be specified per channel)
                filter_parts.append(f"[{audio_input_idx}:a]adelay={delay_ms}|{delay_ms}[{label}]")

            # Mix all delayed audio tracks together with original video audio (at 20% volume)
            # Collect all audio labels
            audio_labels = [f"[a{i}]" for i in range(len(audio_files))]
            all_audio = '[orig]' + ''.join(audio_labels)
            num_inputs = len(audio_files) + 1  # +1 for original video audio

            # Mix all audio with dropout_transition=0 to allow immediate overlaps
            filter_parts.append(f"{all_audio}amix=inputs={num_inputs}:duration=first:dropout_transition=0,volume={num_inputs}[aout]")

            filter_complex = ';'.join(filter_parts)

            # Complete ffmpeg command
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '0:v',  # Map video from input 0
                '-map', '[aout]',  # Map mixed audio output
                '-c:v', 'copy',  # Copy video codec (no re-encoding)
                '-c:a', 'aac',  # Encode audio as AAC
                '-b:a', '192k',  # Audio bitrate
                str(output_path)
            ])

            print(f"Running ffmpeg to generate video...")
            print(f"Command: {' '.join(cmd)}")

            # Run ffmpeg
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"FFmpeg stderr: {result.stderr}")
                raise RuntimeError(f"ffmpeg failed with return code {result.returncode}: {result.stderr}")

            print(f"Video generated successfully: {output_filename}")
            return output_filename

    except Exception as e:
        print("=" * 50)
        print("ERROR in generate_commentary_video:")
        print(traceback.format_exc())
        print("=" * 50)
        raise


def list_videos():
    """List all MP4 files in the videos directory."""
    videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
    videos_dir.mkdir(exist_ok=True)

    # Get all MP4 files
    video_files = [f.name for f in videos_dir.glob('*.mp4')]
    return video_files


async def analyze_video(filename: str):
    """Analyze a video file using Gemini API and extract highlights."""
    try:
        # Initialize Gemini client
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Get video path
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
        video_path = videos_dir / filename

        if not video_path.exists():
            raise FileNotFoundError(f"Video file {filename} not found")

        # Ensure video has audio (add silent audio if needed)
        # This prevents Gemini API errors on muted videos
        video_path_with_audio = ensure_video_has_audio(video_path)

        # Upload video to Gemini File API
        print(f"Uploading video: {video_path_with_audio}")
        uploaded_file = client.files.upload(file=str(video_path_with_audio))
        file_name = uploaded_file.name
        
        # Wait for file to be processed and become ACTIVE
        print(f"Uploaded file {file_name}, waiting for processing...")
        max_retries = 60  # Wait up to 60 seconds
        retry_count = 0
        
        while retry_count < max_retries:
            file_info = client.files.get(name=file_name)
            
            if file_info.state.name == "ACTIVE":
                print(f"File {file_name} is ready for analysis!")
                break
            
            print(f"File state: {file_info.state.name}. Waiting...")
            time.sleep(1)
            retry_count += 1
        
        if retry_count == max_retries:
            raise TimeoutError("File processing timeout")
        
        file_uri = uploaded_file.uri
        
        # ============================================================
        # NEW: Use Graph-Based LLM System for Analysis
        # ============================================================
        print("\n🎬 Using Graph-Based Commentary System")
        orchestrator = GraphOrchestrator(api_key=GEMINI_API_KEY)
        
        # Process video through graph system
        node_outputs, metadata = orchestrator.process_video(file_uri)
        
        # Convert NodeOutput objects to highlight format
        highlights = []
        for output in node_outputs:
            highlights.append({
                'start_time': output.start_time,
                'end_time': output.end_time,
                'description': output.description,
                'commentary': output.commentary,
                'intensity': output.intensity,
                'node_used': output.node_used
            })

        # Validate commentary durations
        highlights = validate_commentary_duration(highlights)

        # ============================================================
        # DEBUG MODE: Skip TTS and video generation if enabled
        # ============================================================
        if DEBUG_COMMENTARY_ONLY:
            print("\n" + "=" * 60)
            print("🔧 DEBUG MODE: Commentary-Only Mode Enabled")
            print("=" * 60)
            print("Skipping TTS audio generation and video creation.")
            print("Returning commentary text only.")
            print(f"\nGenerated {len(highlights)} commentary segments:")
            for i, h in enumerate(highlights):
                print(f"\n  [{i+1}] {h['start_time']} - {h['end_time']}")
                print(f"      Intensity: {h['intensity']}/10 | Node: {h['node_used']}")
                print(f"      Commentary: {h['commentary']}")
            print("\n" + "=" * 60)
            print("To disable debug mode: Remove DEBUG_COMMENTARY_ONLY from .env")
            print("=" * 60 + "\n")

            # Return just the highlights without audio or video
            return {
                'highlights': highlights,
                'generated_video': None,
                'metadata': metadata,
                'debug_mode': True
            }

        # Generate TTS audio for each highlight's commentary
        print("Generating TTS audio for commentary...")
        if ELEVENLABS_API_KEY:
            try:
                tts_generator = TTSGenerator(
                    api_key=ELEVENLABS_API_KEY,
                    default_voice_id="nrD2uNU2IUYtedZegcGx"
                )

                quota_error_detected = False
                for i, highlight in enumerate(highlights):
                    print(f"Generating audio for highlight {i+1}/{len(highlights)}...")
                    print(f"  Commentary text: {highlight['commentary'][:100]}...")
                    audio_base64 = tts_generator.generate_audio(highlight['commentary'])
                    if audio_base64:
                        print(f"  [OK] Audio generated ({len(audio_base64)} chars)")
                        highlight['audio_base64'] = audio_base64
                    else:
                        print(f"  [WARN]  TTS returned empty audio for highlight {i+1}")
                        highlight['audio_base64'] = ""

                        # If first attempt fails, it's likely a quota issue
                        if i == 0:
                            quota_error_detected = True
                            print(f"")
                            print(f"[WARN]  First TTS request failed - likely a quota or API issue.")
                            print(f"   Continuing to process remaining segments, but video may have no audio.")
                            print(f"")
            except Exception as e:
                print(f"[WARN]  TTS generation failed: {str(e)}")
                print(traceback.format_exc())
                for highlight in highlights:
                    highlight['audio_base64'] = ""
        else:
            print("[WARN]  ELEVENLABS_API_KEY not found, skipping TTS generation")
            for highlight in highlights:
                highlight['audio_base64'] = ""

        # Generate video with commentary
        print("Generating video with commentary...")
        output_filename = generate_commentary_video(video_path, highlights)
        print(f"Commentary video saved as: {output_filename}")

        # Add output filename and metadata to response
        return {
            'highlights': highlights,
            'generated_video': output_filename,
            'metadata': metadata
        }
    
    except Exception as e:
        print("=" * 50)
        print("ERROR in analyze_video:")
        print(traceback.format_exc())
        print("=" * 50)
        raise

