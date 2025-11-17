"""
Real-time streaming pipeline for video commentary generation.

Implements a producer-consumer pattern with async queues to stream video chunks
as soon as commentary is generated, enabling playback to start while generation continues.

Pipeline stages:
1. Event Detection (streaming per 30s interval) → event_queue
2. Commentary Generation (per interval) → commentary_queue
3. TTS Audio Generation (parallel) → audio_queue
4. Video Chunk Creation → chunk_queue
5. SSE Event Emission → frontend
"""

import asyncio
import json
import subprocess
import time
import traceback
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional
from google import genai
from google.genai import types

from . import GEMINI_API_KEY, ELEVENLABS_API_KEY
from .analysis.event_detector import EventDetector
from .commentary.commentary_generator import CommentaryGenerator
from .audio.tts_generator import TTSGenerator
from .video.video_processor import VideoProcessor
from .video.time_utils import calculate_video_intervals, seconds_to_time, parse_time_to_seconds


class StreamingPipeline:
    """
    Real-time streaming pipeline that delivers video chunks as soon as they're ready.

    Uses async queues to connect pipeline stages:
    - Event Queue: Detected events per 30s interval
    - Commentary Queue: Generated commentary per interval
    - Audio Queue: TTS audio for each commentary
    - Chunk Queue: Video chunks ready for streaming
    """

    def __init__(self, api_key: str, elevenlabs_api_key: Optional[str] = None):
        """
        Initialize streaming pipeline.

        Args:
            api_key: Gemini API key
            elevenlabs_api_key: ElevenLabs API key (optional)
        """
        self.api_key = api_key
        self.elevenlabs_api_key = elevenlabs_api_key

        # Initialize components
        self.event_detector = EventDetector(api_key=api_key)
        self.commentary_generator = CommentaryGenerator(api_key=api_key)
        self.video_processor = VideoProcessor()

        if elevenlabs_api_key:
            self.tts_generator = TTSGenerator(
                api_key=elevenlabs_api_key,
                default_voice_id="nrD2uNU2IUYtedZegcGx"
            )
        else:
            self.tts_generator = None

        # Session tracking
        self.session_id = None
        self.video_path = None
        self.file_uri = None
        self.video_duration = 0.0

    async def process_video_stream(
        self,
        filename: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process video and stream events as chunks become available.

        Args:
            filename: Name of video file in videos/ directory

        Yields:
            SSE events with chunk URLs and progress updates
        """
        try:
            # Generate session ID for this processing run
            from datetime import datetime
            self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            yield {
                'type': 'status',
                'message': 'Starting video analysis...',
                'progress': 0
            }

            # Step 1: Prepare video
            videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
            self.video_path = videos_dir / filename

            if not self.video_path.exists():
                raise FileNotFoundError(f"Video file {filename} not found")

            yield {
                'type': 'status',
                'message': 'Preparing video...',
                'progress': 5
            }

            # Ensure video has audio
            video_path_with_audio = self.video_processor.ensure_video_has_audio(self.video_path)
            self.video_duration = self.video_processor.get_video_duration(video_path_with_audio)

            # Step 2: Upload to Gemini
            yield {
                'type': 'status',
                'message': 'Uploading video to analysis service...',
                'progress': 10
            }

            client = genai.Client(api_key=self.api_key)
            uploaded_file = client.files.upload(file=str(video_path_with_audio))
            file_name = uploaded_file.name

            # Wait for file to be processed
            max_retries = 60
            retry_count = 0

            while retry_count < max_retries:
                file_info = client.files.get(name=file_name)

                if file_info.state.name == "ACTIVE":
                    break

                await asyncio.sleep(1)
                retry_count += 1

            if retry_count == max_retries:
                raise TimeoutError("File processing timeout")

            self.file_uri = uploaded_file.uri

            yield {
                'type': 'status',
                'message': f'Video ready for analysis ({self.video_duration:.1f}s)',
                'progress': 15
            }

            # Step 3: Create async queues
            event_queue = asyncio.Queue()
            commentary_queue = asyncio.Queue()
            audio_queue = asyncio.Queue()
            chunk_queue = asyncio.Queue()
            sse_event_queue = asyncio.Queue()  # For progress events from all stages

            # Step 4: Launch pipeline stages concurrently
            print(f"\n[STREAMING] Starting pipeline stages...")

            # Create tasks for all pipeline stages
            tasks = [
                asyncio.create_task(
                    self._detect_events_streaming(event_queue, sse_event_queue)
                ),
                asyncio.create_task(
                    self._generate_commentary_streaming(event_queue, commentary_queue, sse_event_queue)
                ),
                asyncio.create_task(
                    self._generate_audio_parallel(commentary_queue, audio_queue)
                ),
                asyncio.create_task(
                    self._create_video_chunks(audio_queue, chunk_queue, video_path_with_audio)
                ),
            ]

            # Step 5: Consume events from both chunk_queue and sse_event_queue
            chunk_index = 0
            total_chunks_expected = self._estimate_chunks()
            chunks_complete = False
            events_complete = False

            # Create pending tasks for getting from both queues
            pending_tasks = set()
            chunk_task = asyncio.create_task(chunk_queue.get())
            sse_task = asyncio.create_task(sse_event_queue.get())
            pending_tasks.add(chunk_task)
            pending_tasks.add(sse_task)

            while not (chunks_complete and events_complete):
                try:
                    # Wait for whichever event comes first
                    done, pending = await asyncio.wait(
                        pending_tasks,
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=120.0
                    )

                    pending_tasks = pending

                    for task in done:
                        if task == chunk_task:
                            chunk_data = task.result()

                            if chunk_data is None:
                                # All chunks processed
                                print(f"[STREAMING] All chunks received (total: {chunk_index})")
                                chunks_complete = True
                            else:
                                # Calculate progress
                                progress = 15 + int((chunk_index / max(total_chunks_expected, 1)) * 80)

                                # Emit chunk ready event
                                yield {
                                    'type': 'chunk_ready',
                                    'index': chunk_data['index'],
                                    'url': chunk_data['url'],
                                    'start_time': chunk_data['start_time'],
                                    'end_time': chunk_data['end_time'],
                                    'progress': min(progress, 95)
                                }

                                chunk_index += 1

                            # Create new task for next chunk (unless complete)
                            if not chunks_complete:
                                chunk_task = asyncio.create_task(chunk_queue.get())
                                pending_tasks.add(chunk_task)

                        elif task == sse_task:
                            sse_event = task.result()

                            if sse_event is None:
                                # No more SSE events
                                print(f"[STREAMING] SSE event stream complete")
                                events_complete = True
                            else:
                                # Emit progress event
                                yield sse_event

                            # Create new task for next SSE event (unless complete)
                            if not events_complete:
                                sse_task = asyncio.create_task(sse_event_queue.get())
                                pending_tasks.add(sse_task)

                except asyncio.TimeoutError:
                    print(f"[STREAMING] Timeout waiting for events")
                    # Check if tasks are still running
                    if all(task.done() for task in tasks):
                        print(f"[STREAMING] All tasks completed, ending stream")
                        break
                    # Otherwise continue waiting
                    continue

            # Wait for all tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)

            # Step 6: Create final concatenated video (background)
            yield {
                'type': 'status',
                'message': 'Finalizing video...',
                'progress': 95
            }

            final_video = await self._create_final_video(chunk_index)

            # Completion event
            final_video_url = f'/videos/generated/{final_video}' if final_video else ''
            yield {
                'type': 'complete',
                'chunks': chunk_index,
                'final_video': final_video_url,
                'progress': 100
            }

        except Exception as e:
            print(f"[STREAMING] ERROR: {e}")
            print(traceback.format_exc())
            yield {
                'type': 'error',
                'message': str(e)
            }

    async def _detect_events_streaming(self, event_queue: asyncio.Queue, sse_event_queue: asyncio.Queue):
        """
        Stage 1: Detect events in 30-second intervals and push to queue.

        Args:
            event_queue: Queue to push detected events
            sse_event_queue: Queue to push SSE progress events
        """
        try:
            print(f"[STREAMING] Starting event detection...")

            # Calculate intervals
            intervals = calculate_video_intervals(self.video_duration, 30)
            total_intervals = len(intervals)

            # Accumulate all events for saving to events.json
            all_events = []

            for i, (start, end) in enumerate(intervals, 1):
                print(f"[STREAMING] Analyzing interval {i}/{total_intervals}: {seconds_to_time(start)} - {seconds_to_time(end)}")

                # Detect events for this interval
                events = self.event_detector.detect_events_for_interval(
                    file_uri=self.file_uri,
                    interval_start=int(start),
                    interval_end=int(end)
                )

                # Accumulate events
                all_events.extend(events)

                # Save accumulated events to events.json after each interval
                self.event_detector._save_events(all_events)

                # Push to queue immediately (don't wait for other intervals)
                await event_queue.put({
                    'interval': (int(start), int(end)),
                    'events': events,
                    'interval_index': i - 1
                })

                print(f"[STREAMING] Pushed {len(events)} events from interval {i} to queue (total: {len(all_events)})")

                # Emit SSE event for progress tracking
                await sse_event_queue.put({
                    'type': 'events_detected',
                    'count': len(events),
                    'interval': [int(start), int(end)],
                    'interval_index': i - 1,
                    'total_intervals': total_intervals
                })

            # Signal completion
            await event_queue.put(None)
            print(f"[STREAMING] Event detection completed - saved {len(all_events)} total events to events.json")

        except Exception as e:
            print(f"[STREAMING] Event detection error: {e}")
            print(traceback.format_exc())
            await event_queue.put(None)

    async def _generate_commentary_streaming(
        self,
        event_queue: asyncio.Queue,
        commentary_queue: asyncio.Queue,
        sse_event_queue: asyncio.Queue
    ):
        """
        Stage 2: Generate commentary for each interval immediately.

        Args:
            event_queue: Input queue with detected events
            commentary_queue: Output queue for generated commentaries
            sse_event_queue: Queue to push SSE progress events
        """
        try:
            print(f"[STREAMING] Starting commentary generation...")

            interval_index = 0

            # Accumulate all commentaries for saving to commentary.json
            all_commentaries = []

            while True:
                event_batch = await event_queue.get()

                if event_batch is None:
                    print(f"[STREAMING] No more events to process")
                    break

                interval = event_batch['interval']
                events = event_batch['events']

                print(f"[STREAMING] Generating commentary for interval {interval} ({len(events)} events)")

                if not events:
                    print(f"[STREAMING] No events in interval {interval}, skipping commentary")
                    interval_index += 1
                    continue

                # Generate commentary for just these events
                # Use synchronous call wrapped in executor to avoid blocking
                try:
                    commentaries = await asyncio.to_thread(
                        self.commentary_generator.generate_commentary,
                        events=[e.model_dump() for e in events],
                        video_duration=interval[1],  # Use interval end as max duration
                        use_streaming=False
                    )

                    # Push each commentary to queue immediately
                    for commentary in commentaries:
                        # Accumulate commentaries
                        all_commentaries.append(commentary)

                        # Save accumulated commentaries to commentary.json
                        self.commentary_generator._save_commentaries(all_commentaries)

                        await commentary_queue.put({
                            'commentary': commentary,
                            'interval_index': interval_index
                        })

                        print(f"[STREAMING] Pushed commentary to queue: {commentary.start_time} - {commentary.end_time} (total: {len(all_commentaries)})")

                        # Emit SSE event for progress tracking
                        await sse_event_queue.put({
                            'type': 'commentary_ready',
                            'text': commentary.commentary,
                            'start': commentary.start_time,
                            'end': commentary.end_time
                        })

                except Exception as e:
                    print(f"[STREAMING] Commentary generation failed for interval {interval}: {e}")
                    # Continue with next interval even if this one fails

                interval_index += 1

            # Signal completion
            await commentary_queue.put(None)
            await sse_event_queue.put(None)  # Signal SSE stream completion
            print(f"[STREAMING] Commentary generation completed - saved {len(all_commentaries)} total commentaries to commentary.json")

        except Exception as e:
            print(f"[STREAMING] Commentary generation error: {e}")
            print(traceback.format_exc())
            await commentary_queue.put(None)
            await sse_event_queue.put(None)  # Signal SSE stream completion even on error

    async def _generate_audio_parallel(
        self,
        commentary_queue: asyncio.Queue,
        audio_queue: asyncio.Queue
    ):
        """
        Stage 3: Generate TTS audio in parallel (up to 5 concurrent requests).

        Args:
            commentary_queue: Input queue with commentaries
            audio_queue: Output queue for audio data
        """
        try:
            print(f"[STREAMING] Starting TTS generation...")

            if not self.tts_generator:
                print(f"[STREAMING] No TTS generator available, skipping audio generation")
                while True:
                    commentary_data = await commentary_queue.get()
                    if commentary_data is None:
                        break
                    # Pass through without audio
                    await audio_queue.put({
                        'commentary': commentary_data['commentary'],
                        'audio_base64': None,
                        'interval_index': commentary_data['interval_index']
                    })
                await audio_queue.put(None)
                return

            tasks = set()
            max_concurrent = 5  # ElevenLabs rate limit

            while True:
                commentary_data = await commentary_queue.get()

                if commentary_data is None:
                    print(f"[STREAMING] No more commentaries to process")
                    break

                commentary = commentary_data['commentary']
                interval_index = commentary_data['interval_index']

                print(f"[STREAMING] Creating TTS task for: {commentary.start_time} - {commentary.end_time}")

                # Create task for this TTS request
                task = asyncio.create_task(
                    self._generate_single_audio(commentary, interval_index, audio_queue)
                )
                tasks.add(task)

                # Limit concurrency
                if len(tasks) >= max_concurrent:
                    done, tasks = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )

            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Signal completion
            await audio_queue.put(None)
            print(f"[STREAMING] TTS generation completed")

        except Exception as e:
            print(f"[STREAMING] TTS generation error: {e}")
            print(traceback.format_exc())
            await audio_queue.put(None)

    async def _generate_single_audio(
        self,
        commentary,
        interval_index: int,
        audio_queue: asyncio.Queue
    ):
        """
        Generate audio for a single commentary and push to queue.

        Args:
            commentary: Commentary object
            interval_index: Index of the interval
            audio_queue: Queue to push audio data
        """
        try:
            print(f"[STREAMING] Generating TTS for: {commentary.commentary[:50]}...")

            # Generate audio (run in thread to avoid blocking)
            audio_base64 = await asyncio.to_thread(
                self.tts_generator.generate_audio,
                commentary.commentary
            )

            if audio_base64:
                print(f"[STREAMING] TTS completed ({len(audio_base64)} chars)")
            else:
                print(f"[STREAMING] TTS returned empty audio")

            await audio_queue.put({
                'commentary': commentary,
                'audio_base64': audio_base64,
                'interval_index': interval_index
            })

        except Exception as e:
            print(f"[STREAMING] TTS generation failed: {e}")
            # Push without audio
            await audio_queue.put({
                'commentary': commentary,
                'audio_base64': None,
                'interval_index': interval_index
            })

    async def _create_video_chunks(
        self,
        audio_queue: asyncio.Queue,
        chunk_queue: asyncio.Queue,
        video_path: Path
    ):
        """
        Stage 4: Create continuous video chunks with no gaps.

        Each chunk spans from the previous chunk's end to the current commentary's end_time,
        ensuring full video coverage:
        - Chunk 0: [0, commentary_1.end_time] with commentary_1 overlaid
        - Chunk 1: [commentary_1.end_time, commentary_2.end_time] with commentary_2 overlaid
        - Chunk N: [commentary_N-1.end_time, commentary_N.end_time] with commentary_N overlaid
        - Final: [last_end_time, video_duration] with no commentary

        Note: Collects all commentaries first and sorts by start_time to ensure
        chronological chunk creation, even when TTS completes out of order.

        Args:
            audio_queue: Input queue with audio data
            chunk_queue: Output queue for video chunks
            video_path: Path to original video
        """
        try:
            print(f"[STREAMING] Starting video chunk creation...")

            # Create output directory for chunks
            videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
            streaming_dir = videos_dir / 'streaming' / self.session_id
            streaming_dir.mkdir(exist_ok=True, parents=True)

            # Stage 1: Collect all commentaries from the parallel TTS queue
            # (they arrive in completion order, not chronological order)
            commentaries = []
            while True:
                audio_data = await audio_queue.get()
                if audio_data is None:
                    break
                commentaries.append(audio_data)

            print(f"[STREAMING] Collected {len(commentaries)} commentaries, sorting chronologically...")

            # Stage 2: Sort by start_time to ensure correct chunk boundaries
            # This is critical because parallel TTS completes out of order
            commentaries.sort(key=lambda x: parse_time_to_seconds(x['commentary'].start_time))

            # Stage 3: Create chunks in chronological order
            chunk_index = 0
            chunk_start = 0.0  # First chunk always starts at video beginning

            for audio_data in commentaries:
                commentary = audio_data['commentary']
                audio_base64 = audio_data['audio_base64']

                # Chunk ends at this commentary's end_time
                chunk_end = parse_time_to_seconds(commentary.end_time)

                # Validate chunk duration (skip if too small or zero)
                chunk_duration = chunk_end - chunk_start
                if chunk_duration < 0.1:
                    print(f"[STREAMING] Skipping chunk {chunk_index}: duration too small ({chunk_duration:.2f}s)")
                    continue

                print(f"[STREAMING] Creating chunk {chunk_index}: {seconds_to_time(chunk_start)} - {seconds_to_time(chunk_end)}")

                try:
                    # Create chunk from chunk_start to chunk_end
                    # Commentary will be overlaid at its specific time within the chunk
                    chunk_path = await asyncio.to_thread(
                        self._create_single_chunk,
                        video_path,
                        chunk_start,
                        chunk_end,
                        commentary,
                        audio_base64,
                        chunk_index,
                        streaming_dir
                    )

                    # Generate URL for frontend
                    chunk_url = f"/videos/streaming/{self.session_id}/chunk_{chunk_index}.mp4"

                    await chunk_queue.put({
                        'path': chunk_path,
                        'url': chunk_url,
                        'index': chunk_index,
                        'start_time': seconds_to_time(chunk_start),
                        'end_time': seconds_to_time(chunk_end)
                    })

                    print(f"[STREAMING] Chunk {chunk_index} ready: {chunk_url}")

                    # Next chunk starts where this one ended
                    chunk_start = chunk_end
                    chunk_index += 1

                except Exception as e:
                    print(f"[STREAMING] Chunk creation failed for index {chunk_index}: {e}")
                    print(traceback.format_exc())
                    # Continue with next chunk even if this one fails
                    continue

            # Stage 4: Create final chunk from last commentary end to video end
            final_chunk_duration = self.video_duration - chunk_start
            if chunk_start <= self.video_duration and final_chunk_duration >= 0.1:
                print(f"[STREAMING] Creating final chunk {chunk_index}: {seconds_to_time(chunk_start)} - {seconds_to_time(self.video_duration)}")

                try:
                    chunk_path = await asyncio.to_thread(
                        self._create_single_chunk,
                        video_path,
                        chunk_start,
                        self.video_duration,
                        None,  # No commentary for final chunk
                        None,  # No audio
                        chunk_index,
                        streaming_dir
                    )

                    chunk_url = f"/videos/streaming/{self.session_id}/chunk_{chunk_index}.mp4"

                    await chunk_queue.put({
                        'path': chunk_path,
                        'url': chunk_url,
                        'index': chunk_index,
                        'start_time': seconds_to_time(chunk_start),
                        'end_time': seconds_to_time(self.video_duration)
                    })

                    print(f"[STREAMING] Final chunk {chunk_index} ready")
                    chunk_index += 1

                except Exception as e:
                    print(f"[STREAMING] Final chunk creation failed: {e}")
                    print(traceback.format_exc())

            # Signal completion
            await chunk_queue.put(None)
            print(f"[STREAMING] Video chunk creation completed ({chunk_index} chunks)")

        except Exception as e:
            print(f"[STREAMING] Chunk creation error: {e}")
            print(traceback.format_exc())
            await chunk_queue.put(None)

    def _create_single_chunk(
        self,
        video_path: Path,
        chunk_start: float,
        chunk_end: float,
        commentary,
        audio_base64: Optional[str],
        chunk_index: int,
        output_dir: Path
    ) -> Path:
        """
        Create a single video chunk spanning chunk_start to chunk_end.

        If commentary is provided, it will be overlaid at the exact time
        specified by the commentary start_time (relative to chunk start).

        This is a SYNCHRONOUS method that will be run in a thread.

        Args:
            video_path: Path to original video
            chunk_start: Start time in seconds (relative to original video)
            chunk_end: End time in seconds (relative to original video)
            commentary: Commentary object (or None for chunks without commentary)
            audio_base64: Base64 encoded audio (or None)
            chunk_index: Index of this chunk
            output_dir: Directory to save chunk

        Returns:
            Path to created chunk file
        """
        import base64
        import subprocess
        import tempfile

        chunk_filename = f"chunk_{chunk_index}.mp4"
        chunk_path = output_dir / chunk_filename

        if commentary and audio_base64:
            # Create chunk with audio overlay
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                audio_file = temp_path / "commentary.mp3"

                # Decode and save audio
                audio_bytes = base64.b64decode(audio_base64)
                audio_file.write_bytes(audio_bytes)

                # Calculate delay relative to chunk start
                # Commentary start_time is absolute (relative to original video)
                # We need delay relative to this chunk's start (exact timing)
                commentary_start = parse_time_to_seconds(commentary.start_time)
                delay_from_chunk_start = commentary_start - chunk_start
                delay_ms = int(delay_from_chunk_start * 1000)

                # Ensure delay is not negative
                if delay_ms < 0:
                    print(f"[WARNING] Negative delay calculated: {delay_ms}ms, setting to 0ms")
                    delay_ms = 0

                # FFmpeg command to create chunk with audio overlay
                cmd = [
                    self.video_processor.ffmpeg_exe, '-y',
                    '-ss', str(chunk_start),
                    '-to', str(chunk_end),
                    '-i', str(video_path),
                    '-i', str(audio_file),
                    '-filter_complex',
                    f'[0:a]volume=0.2[orig];[1:a]adelay={delay_ms}|{delay_ms}[comm];[orig][comm]amix=inputs=2:duration=first[aout]',
                    '-map', '0:v',
                    '-map', '[aout]',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-c:a', 'aac',
                    '-ar', '44100',
                    '-b:a', '192k',
                    '-movflags', '+faststart',
                    str(chunk_path)
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        else:
            # Create chunk without commentary (just original video segment)
            cmd = [
                self.video_processor.ffmpeg_exe, '-y',
                '-ss', str(chunk_start),
                '-to', str(chunk_end),
                '-i', str(video_path),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-c:a', 'aac',
                '-ar', '44100',
                '-b:a', '192k',
                '-movflags', '+faststart',
                str(chunk_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

        return chunk_path

    async def _create_final_video(self, chunk_count: int) -> str:
        """
        Create final concatenated video from all chunks.

        Args:
            chunk_count: Number of chunks to concatenate

        Returns:
            Filename of final video
        """
        try:
            if chunk_count == 0:
                return ""

            print(f"[STREAMING] Creating final video from {chunk_count} chunks...")

            # Get chunk directory
            videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
            streaming_dir = videos_dir / 'streaming' / self.session_id

            # Create concat list
            concat_file = streaming_dir / 'concat_list.txt'

            with open(concat_file, 'w') as f:
                for i in range(chunk_count):
                    chunk_path = streaming_dir / f"chunk_{i}.mp4"
                    if chunk_path.exists():
                        f.write(f"file '{chunk_path.absolute()}'\n")

            # Output path
            output_dir = videos_dir / 'generated-videos'
            output_dir.mkdir(exist_ok=True, parents=True)

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"commentary_{timestamp}.mp4"
            output_path = output_dir / output_filename

            # Concatenate chunks
            cmd = [
                self.video_processor.ffmpeg_exe, '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                str(output_path)
            ]

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                print(f"[STREAMING] Final video creation failed: {result.stderr}")
                return ""

            print(f"[STREAMING] Final video created: {output_filename}")
            return output_filename

        except Exception as e:
            print(f"[STREAMING] Error creating final video: {e}")
            return ""

    def _estimate_chunks(self) -> int:
        """Estimate number of chunks based on video duration."""
        # Rough estimate: 1 chunk per 30 seconds of video
        return max(1, int(self.video_duration / 30))


async def streaming_pipeline(filename: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Main entry point for streaming pipeline.

    Args:
        filename: Video filename in videos/ directory

    Yields:
        SSE events with chunk URLs and progress updates
    """
    pipeline = StreamingPipeline(
        api_key=GEMINI_API_KEY,
        elevenlabs_api_key=ELEVENLABS_API_KEY
    )

    async for event in pipeline.process_video_stream(filename):
        yield event
