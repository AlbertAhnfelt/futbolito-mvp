"""
Video processing utilities using FFmpeg.
Handles video operations, audio overlay, and metadata extraction.
"""

import base64
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from imageio_ffmpeg import get_ffmpeg_exe

from .time_utils import parse_time_to_seconds


class VideoProcessor:
    """
    Handles video processing operations using FFmpeg.

    Provides utilities for:
    - Ensuring videos have audio tracks
    - Overlaying commentary audio with delays
    - Extracting video metadata
    """

    def __init__(self):
        """Initialize video processor with FFmpeg executable."""
        self.ffmpeg_exe = get_ffmpeg_exe()
        print(f"[VIDEO PROCESSOR] Using FFmpeg from: {self.ffmpeg_exe}")

    def ensure_video_has_audio(self, video_path: Path) -> Path:
        """
        Ensure video has an audio track. If not, add a silent audio track.

        This prevents Gemini API errors when processing muted videos.

        Args:
            video_path: Path to the video file

        Returns:
            Path to video with audio (either original or a temp file with audio added)
        """
        try:
            # Check if video has audio track
            probe_cmd = [
                self.ffmpeg_exe, '-i', str(video_path),
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
                print("[VIDEO PROCESSOR] WARNING: Video has no audio track. Adding silent audio...")

                # Create a temporary file with audio
                temp_dir = Path(tempfile.gettempdir())
                temp_video = temp_dir / f"video_with_audio_{video_path.stem}.mp4"

                # Add silent audio track
                cmd = [
                    self.ffmpeg_exe, '-y',
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
                    print(f"[VIDEO PROCESSOR] Warning: Failed to add audio track: {result.stderr}")
                    return video_path

                print(f"[VIDEO PROCESSOR] SUCCESS: Silent audio track added: {temp_video}")
                return temp_video
            else:
                print("[VIDEO PROCESSOR] SUCCESS: Video already has audio track")
                return video_path

        except Exception as e:
            print(f"[VIDEO PROCESSOR] Warning: Could not check/add audio: {str(e)}")
            return video_path

    def get_video_duration(self, video_path: Path) -> float:
        """
        Get video duration in seconds using ffprobe.

        Args:
            video_path: Path to the video file

        Returns:
            Duration in seconds

        Raises:
            RuntimeError: If ffprobe fails
        """
        try:
            cmd = [
                self.ffmpeg_exe.replace('ffmpeg', 'ffprobe'),
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            duration = float(result.stdout.strip())
            print(f"[VIDEO PROCESSOR] Video duration: {duration:.2f} seconds")
            return duration

        except Exception as e:
            print(f"[VIDEO PROCESSOR] Warning: Could not get duration via ffprobe: {e}")
            # Fallback: try using ffmpeg
            try:
                cmd = [
                    self.ffmpeg_exe,
                    '-i', str(video_path),
                    '-f', 'null', '-'
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                # Parse duration from stderr (ffmpeg outputs to stderr)
                import re
                match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', result.stderr)
                if match:
                    h, m, s = match.groups()
                    duration = int(h) * 3600 + int(m) * 60 + float(s)
                    print(f"[VIDEO PROCESSOR] Video duration (fallback): {duration:.2f} seconds")
                    return duration

            except Exception as fallback_error:
                print(f"[VIDEO PROCESSOR] Fallback also failed: {fallback_error}")

            raise RuntimeError(f"Could not determine video duration: {e}")

    def generate_commentary_video(
        self,
        video_path: Path,
        commentaries: List[Dict[str, Any]],
        output_dir: Optional[Path] = None
    ) -> str:
        """
        Generate a video with commentary audio overlaid at specific timestamps.

        IMPORTANT: Audio is added with a 1-second delay from start_time.

        Args:
            video_path: Path to the original video file
            commentaries: List of commentary dicts with audio_base64, start_time, end_time
            output_dir: Directory to save output (default: videos/generated-videos/)

        Returns:
            Filename of the generated video

        Raises:
            RuntimeError: If ffmpeg fails
        """
        try:
            print(f"\n{'='*60}")
            print(f"GENERATING COMMENTARY VIDEO")
            print(f"{'='*60}")

            # Set output directory
            if output_dir is None:
                videos_dir = Path(__file__).parent.parent.parent.parent.parent / 'videos'
                output_dir = videos_dir / 'generated-videos'

            output_dir = Path(output_dir)
            output_dir.mkdir(exist_ok=True, parents=True)

            # Generate output filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"commentary_{timestamp}.mp4"
            output_path = output_dir / output_filename

            # Create temporary directory for audio files
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                audio_files = []

                # Save each audio_base64 to temporary MP3 files
                print(f"[VIDEO PROCESSOR] Saving {len(commentaries)} audio files...")
                for i, commentary in enumerate(commentaries):
                    if not commentary.get('audio_base64'):
                        print(f"[VIDEO PROCESSOR] Warning: No audio for commentary {i+1}, skipping...")
                        continue

                    # Decode base64 audio
                    audio_bytes = base64.b64decode(commentary['audio_base64'])

                    # Save to temporary file
                    audio_file = temp_path / f"audio_{i}.mp3"
                    audio_file.write_bytes(audio_bytes)

                    # Calculate delay in milliseconds
                    # IMPORTANT: Add 1 second delay as per requirements
                    start_seconds = parse_time_to_seconds(commentary['start_time'])
                    delay_seconds = start_seconds + 1.0  # Add 1-second delay
                    delay_ms = int(delay_seconds * 1000)

                    audio_files.append({
                        'path': audio_file,
                        'delay_ms': delay_ms,
                        'index': i,
                        'start_time': commentary['start_time']
                    })

                    print(f"[VIDEO PROCESSOR]   Audio {i+1}: {commentary['start_time']} → {delay_ms}ms delay (with +1s)")

                if not audio_files:
                    print(f"\n[WARN] No valid audio files found!")
                    print(f"   Total commentaries: {len(commentaries)}")
                    print(f"   Commentaries with audio: 0")
                    print(f"\n[INFO] Generating video without commentary audio...")
                    print(f"   The video will be created with original audio only.")

                    # Copy the original video as the output
                    shutil.copy(video_path, output_path)
                    print(f"[VIDEO PROCESSOR] Video saved (original audio only): {output_filename}")
                    return output_filename

                # Build ffmpeg command
                print(f"[VIDEO PROCESSOR] Building ffmpeg command...")
                cmd = [self.ffmpeg_exe, '-y', '-i', str(video_path)]

                # Add all audio inputs
                for audio_info in audio_files:
                    cmd.extend(['-i', str(audio_info['path'])])

                # Build filter_complex
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

                print(f"[VIDEO PROCESSOR] Running ffmpeg to generate video...")

                # Run ffmpeg
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0:
                    print(f"[VIDEO PROCESSOR] FFmpeg stderr: {result.stderr}")
                    raise RuntimeError(f"ffmpeg failed with return code {result.returncode}: {result.stderr}")

                print(f"[VIDEO PROCESSOR] ✓ Video generated successfully: {output_filename}")
                print(f"{'='*60}\n")
                return output_filename

        except Exception as e:
            print(f"[VIDEO PROCESSOR] ERROR: {e}")
            import traceback
            print(traceback.format_exc())
            raise
