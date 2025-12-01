"""
Rate limiter for Gemini API calls to prevent quota exhaustion.

Implements a token bucket algorithm to enforce strict rate limits.
Configured for Gemini 2.5 Flash with conservative 10 RPM limit.
"""

import time
import threading
from typing import Optional


class RateLimiter:
    """
    Thread-safe rate limiter using token bucket algorithm.

    Ensures API calls don't exceed the specified requests per minute (RPM).
    Adds a safety buffer to prevent edge-case quota violations.
    """

    def __init__(self, requests_per_minute: int = 10, safety_buffer: float = 0.5):
        """
        Initialize the rate limiter.

        Args:
            requests_per_minute: Maximum number of requests allowed per minute
            safety_buffer: Additional delay in seconds to add for safety (default: 0.5s)
        """
        self.requests_per_minute = requests_per_minute
        self.safety_buffer = safety_buffer

        # Calculate minimum delay between requests
        self.min_delay = 60.0 / requests_per_minute

        # Track last request timestamp
        self.last_request_time: Optional[float] = None

        # Thread lock for concurrent access
        self._lock = threading.Lock()

        print(f"[RATE_LIMITER] Initialized with {requests_per_minute} RPM "
              f"({self.min_delay:.2f}s between calls + {safety_buffer}s buffer)")

    def wait_if_needed(self) -> float:
        """
        Block execution if necessary to respect rate limits.

        Returns:
            float: The actual sleep time in seconds (0 if no wait needed)
        """
        with self._lock:
            current_time = time.time()

            # First request - no wait needed
            if self.last_request_time is None:
                self.last_request_time = current_time
                return 0.0

            # Calculate time elapsed since last request
            elapsed = current_time - self.last_request_time

            # Calculate required delay (min delay + safety buffer)
            required_delay = self.min_delay + self.safety_buffer

            # If we're going too fast, sleep
            if elapsed < required_delay:
                sleep_time = required_delay - elapsed
                print(f"[RATE_LIMITER] Throttling... Sleeping {sleep_time:.2f}s to respect {self.requests_per_minute} RPM quota")
                time.sleep(sleep_time)

                # Update last request time to now
                self.last_request_time = time.time()
                return sleep_time
            else:
                # Enough time has passed - update timestamp and proceed
                self.last_request_time = current_time
                return 0.0

    def reset(self):
        """Reset the rate limiter state (useful for testing)."""
        with self._lock:
            self.last_request_time = None
            print("[RATE_LIMITER] State reset")


# Global singleton instance for Gemini API calls
# Configured for conservative 10 RPM to stay within free tier limits
gemini_rate_limiter = RateLimiter(requests_per_minute=10, safety_buffer=0.5)
