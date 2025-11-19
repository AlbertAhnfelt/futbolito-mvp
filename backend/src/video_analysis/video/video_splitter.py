"""
Video splitting utility for preprocessing videos into fixed-duration segments.
Uses FFmpeg stream copy for fast, lossless splitting.
"""

import subprocess
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

from .time_utils import calculate_video_intervals, seconds_to_time


@dataclass
class VideoClip:
    """Represents a split video clip."""
    path: Path
    start_time: int  # seconds in original video
    end_time: int  # seconds in original video
    duration: int  # clip duration in seconds
    index: int  # clip index (0-based)


class VideoSplitter:
    """
    Splits videos into fixed-duration segments for analysis.

    Uses FFmpeg with stream copy (-c copy) for fast, lossless splitting
    without re-encoding. This ensures minimal processing time.
    """

    def __init__(self, ffmpeg_exe: str):
        """
        Initialize video splitter.

        Args:
            ffmpeg_exe: Path to FFmpeg executable
        """
        self.ffmpeg_exe = ffmpeg_exe

    def split_video(
        self,
        video_path: Path,
        duration_seconds: float,
        interval_seconds: int = 30,
        output_dir: Path = None
    ) -> List[VideoClip]:
        """
        Split video into fixed-duration segments.

        Args:
            video_path: Path to video file
            duration_seconds: Total video duration in seconds
            interval_seconds: Duration of each segment (default: 30)
            output_dir: Directory to save clips (default: temp directory)

        Returns:
            List of VideoClip objects with paths and metadata

        Example:
            >>> splitter = VideoSplitter(ffmpeg_exe="/path/to/ffmpeg")
            >>> clips = splitter.split_video(
            ...     video_path=Path("video.mp4"),
            ...     duration_seconds=100,
            ...     interval_seconds=30
            ... )
            >>> # Returns 4 clips: [0-30s, 30-60s, 60-90s, 90-100s]
        """
        print(f"\n{'='*60}")
        print(f"VIDEO SPLITTING STARTED")
        print(f"{'='*60}")
        print(f"Video: {video_path.name}")
        print(f"Duration: {seconds_to_time(duration_seconds)} ({duration_seconds}s)")
        print(f"Segment length: {interval_seconds}s")

        # Calculate intervals
        intervals = calculate_video_intervals(duration_seconds, interval_seconds)
        print(f"Total segments to create: {len(intervals)}")

        # Create output directory if not specified
        if output_dir is None:
            import tempfile
            output_dir = Path(tempfile.mkdtemp(prefix="video_clips_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(exist_ok=True, parents=True)

        print(f"Output directory: {output_dir}")

        clips = []

        # Split video into segments
        for i, (start, end) in enumerate(intervals):
            clip_filename = f"clip_{i:03d}_{int(start):04d}_{int(end):04d}.mp4"
            clip_path = output_dir / clip_filename

            print(f"\n[{i+1}/{len(intervals)}] Creating clip: {seconds_to_time(start)} - {seconds_to_time(end)}")
            print(f"  Output: {clip_filename}")

            try:
                # Use FFmpeg with stream copy for fast splitting
                # IMPORTANT: -ss AFTER -i to ensure timestamps are reset to 0
                # This is critical for Gemini to see correct timestamps in the clip
                cmd = [
                    self.ffmpeg_exe,
                    '-y',  # Overwrite output files
                    '-i', str(video_path),  # Input file
                    '-ss', str(start),  # Seek to start time (AFTER -i for accurate timestamps)
                    '-to', str(end),  # End time
                    '-c', 'copy',  # Stream copy (no re-encoding)
                    '-avoid_negative_ts', 'make_zero',  # Reset timestamps to zero
                    str(clip_path)
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    encoding='utf-8',
                    errors='replace'
                )

                if result.returncode != 0:
                    print(f"  ✗ Failed: {result.stderr}")
                    raise RuntimeError(f"FFmpeg failed for clip {i}: {result.stderr}")

                # Verify clip was created
                if not clip_path.exists():
                    raise RuntimeError(f"Clip file not created: {clip_path}")

                # Create VideoClip object
                clip = VideoClip(
                    path=clip_path,
                    start_time=int(start),
                    end_time=int(end),
                    duration=int(end - start),
                    index=i
                )
                clips.append(clip)

                file_size_mb = clip_path.stat().st_size / (1024 * 1024)
                print(f"  ✓ Created: {file_size_mb:.2f} MB")

            except Exception as e:
                print(f"  ✗ Error: {e}")
                raise RuntimeError(f"Failed to create clip {i}: {e}")

        print(f"\n{'='*60}")
        print(f"VIDEO SPLITTING COMPLETED")
        print(f"{'='*60}")
        print(f"Total clips created: {len(clips)}")
        print(f"Output directory: {output_dir}")
        print(f"{'='*60}\n")

        return clips

    def cleanup_clips(self, clips: List[VideoClip]):
        """
        Delete temporary clip files.

        Args:
            clips: List of VideoClip objects to clean up
        """
        print(f"\n[VIDEO SPLITTER] Cleaning up {len(clips)} temporary clips...")

        for clip in clips:
            try:
                if clip.path.exists():
                    clip.path.unlink()
            except Exception as e:
                print(f"[VIDEO SPLITTER] Warning: Failed to delete {clip.path}: {e}")

        # Try to remove parent directory if it's empty
        if clips:
            parent_dir = clips[0].path.parent
            try:
                if parent_dir.exists() and not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
                    print(f"[VIDEO SPLITTER] Removed empty directory: {parent_dir}")
            except Exception as e:
                print(f"[VIDEO SPLITTER] Warning: Failed to remove directory {parent_dir}: {e}")

        print(f"[VIDEO SPLITTER] Cleanup completed")
