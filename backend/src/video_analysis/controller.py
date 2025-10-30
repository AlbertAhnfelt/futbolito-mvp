import json
import time
import traceback
import base64
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel
from elevenlabs import ElevenLabs
from imageio_ffmpeg import get_ffmpeg_exe
from . import GEMINI_API_KEY, ELEVENLABS_API_KEY


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

            print(f"⚠️ Highlight {highlight['start_time']}-{highlight['end_time']}: "
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
    audio_base64: str | None = None


def generate_tts_audio(text: str, voice_id: str) -> str:
    """
    Generate TTS audio using ElevenLabs API and return as base64 string.

    Args:
        text: The text to convert to speech
        voice_id: The ElevenLabs voice ID to use

    Returns:
        Base64 encoded audio data
    """
    try:
        if not ELEVENLABS_API_KEY:
            raise ValueError("ELEVENLABS_API_KEY not found in environment variables")

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # Generate audio using ElevenLabs API
        audio_generator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2"
        )

        # Collect all audio chunks
        audio_bytes = b''
        for chunk in audio_generator:
            audio_bytes += chunk

        # Convert to base64
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        return audio_base64

    except Exception as e:
        print(f"Warning: TTS generation failed for text: {text[:50]}...")
        print(f"Error: {str(e)}")
        return ""


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
                raise ValueError("No valid audio files found in highlights")

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
        
        # Upload video to Gemini File API
        print(f"Uploading video: {video_path}")
        uploaded_file = client.files.upload(file=str(video_path))
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
        
        # Analyze video with Gemini
        response = client.models.generate_content(
            model='models/gemini-2.5-flash',
            contents=types.Content(
                parts=[
                    types.Part(
                        file_data=types.FileData(file_uri=file_uri)
                    ),
                    types.Part(text="""
                    Here is a short clip of a football match. Identify important events in the video.

                    IMPORTANT: Analyze ONLY the visual content of the video. DO NOT use any audio, commentary, or sound from the video.
                    Base your analysis purely on what you can see: player movements, ball trajectory, tackles, passes, shots, celebrations, etc.

                    For each event explain what happens in the video based solely on visual observation.
                    Only identify players if you can visually recognize them (jersey numbers, physical appearance, playing style).
                    Describe precisely what happened with football technical language based on visual analysis only.

                    For each highlight return a json with this format :
                    {
                      start_time : "00:00:00",
                      end_time : "00:00:00",
                      description : "XXX",
                      commentary : "XXX"
                    }

                    The 'description' field should contain technical analysis of what happens.
                    In the 'commentary' field, you are an english TV commentator describing the events briefly.
                    CRITICAL: The commentary must be short enough to say within the event's duration (end_time - start_time).
                    Use approximately 2-3 words per second maximum. For a 5-second event, use ~12 words. For 20 seconds, use ~50 words.
                    No insignificant sentences, only punchy event description and analysis.

                    DO NOT RETURN ANY OTHER TEXT.
                    """)
                ]
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": list[Highlight],
            },
        )
        
        # Parse JSON response
        highlights = json.loads(response.text)

        # Validate commentary durations
        highlights = validate_commentary_duration(highlights)

        # Generate TTS audio for each highlight's commentary
        print("Generating TTS audio for commentary...")
        voice_id = "nrD2uNU2IUYtedZegcGx"  # The voice ID provided by user

        for i, highlight in enumerate(highlights):
            print(f"Generating audio for highlight {i+1}/{len(highlights)}...")
            audio_base64 = generate_tts_audio(highlight['commentary'], voice_id)
            highlight['audio_base64'] = audio_base64

        # Generate video with commentary
        print("Generating video with commentary...")
        output_filename = generate_commentary_video(video_path, highlights)
        print(f"Commentary video saved as: {output_filename}")

        # Add output filename to response
        return {
            'highlights': highlights,
            'generated_video': output_filename
        }
    
    except Exception as e:
        print("=" * 50)
        print("ERROR in analyze_video:")
        print(traceback.format_exc())
        print("=" * 50)
        raise

