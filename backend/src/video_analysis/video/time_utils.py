"""
Time utility functions for video processing.
"""

from typing import List, Dict, Any


def parse_time_to_seconds(time_str: str) -> float:
    """
    Convert time string to seconds.

    Supports HH:MM:SS, MM:SS, or SS formats.

    Args:
        time_str: Time string in HH:MM:SS, MM:SS, or SS format

    Returns:
        Time in seconds as float

    Raises:
        ValueError: If time format is invalid

    Examples:
        >>> parse_time_to_seconds("01:30:45")
        5445.0
        >>> parse_time_to_seconds("15:30")
        930.0
        >>> parse_time_to_seconds("45")
        45.0
    """
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


def seconds_to_time(seconds: float) -> str:
    """
    Convert seconds to HH:MM:SS format.

    Args:
        seconds: Time in seconds

    Returns:
        Time string in HH:MM:SS format

    Examples:
        >>> seconds_to_time(5445)
        "01:30:45"
        >>> seconds_to_time(930)
        "00:15:30"
        >>> seconds_to_time(45.5)
        "00:00:45"
    """
    hours = int(seconds // 3600)
    remaining = seconds % 3600
    minutes = int(remaining // 60)
    secs = int(remaining % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def validate_commentary_duration(commentaries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensure each commentary fits within its duration.

    Uses average speech rate of 2.5 words/second (150 words/minute).
    Only modifies 'commentary' field.

    Args:
        commentaries: List of commentary dictionaries with start_time, end_time, and commentary text

    Returns:
        List of commentaries with validated/truncated text

    Examples:
        >>> commentaries = [{'start_time': '00:00:00', 'end_time': '00:00:10', 'commentary': 'Very long text...'}]
        >>> validated = validate_commentary_duration(commentaries)
    """
    WORDS_PER_SECOND = 2.5  # Conservative estimate for clear commentary

    for commentary in commentaries:
        # Calculate duration for this specific commentary
        start_seconds = parse_time_to_seconds(commentary['start_time'])
        end_seconds = parse_time_to_seconds(commentary['end_time'])
        duration = end_seconds - start_seconds

        # Calculate max words allowed for this duration
        max_words = int(duration * WORDS_PER_SECOND)

        # Check commentary word count
        commentary_words = commentary['commentary'].split()

        if len(commentary_words) > max_words:
            # Truncate at sentence boundary if possible
            truncated = ' '.join(commentary_words[:max_words])

            # Try to end at last complete sentence
            for punct in ['.', '!', '?']:
                if punct in truncated:
                    truncated = truncated.rsplit(punct, 1)[0] + punct
                    break

            print(f"[WARN] Commentary {commentary['start_time']}-{commentary['end_time']}: "
                  f"Truncated from {len(commentary_words)} to {max_words} words "
                  f"(duration: {duration:.1f}s)")

            commentary['commentary'] = truncated

    return commentaries


def calculate_video_intervals(duration_seconds: float, interval_seconds: int = 30) -> List[tuple]:
    """
    Split video duration into intervals.

    Args:
        duration_seconds: Total video duration in seconds
        interval_seconds: Length of each interval (default: 30 seconds)

    Returns:
        List of (start, end) tuples in seconds

    Examples:
        >>> calculate_video_intervals(133, 30)
        [(0, 30), (30, 60), (60, 90), (90, 120), (120, 133)]
    """
    intervals = []
    current_start = 0

    while current_start < duration_seconds:
        current_end = min(current_start + interval_seconds, duration_seconds)
        intervals.append((current_start, current_end))
        current_start = current_end

    return intervals
