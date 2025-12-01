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
from .video.video_splitter import VideoSplitter, VideoClip
from .video.time_utils import calculate_video_intervals, seconds_to_time, parse_time_to_seconds
from .state_manager import StateManager


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
        Initialize streaming pipeline with StateManager integration.

        Args:
            api_key: Gemini API key
            elevenlabs_api_key: ElevenLabs API key (optional)
        """
        self.api_key = api_key
        self.elevenlabs_api_key = elevenlabs_api_key

        # StateManager will be initialized per session
        self.state_manager = None

        # Components (will be re-initialized with StateManager per session)
        self.event_detector = None
        self.commentary_generator = None
        self.video_processor = VideoProcessor()

        if elevenlabs_api_key:
            self.tts_generator = TTSGenerator(api_key=elevenlabs_api_key)
        else:
            self.tts_generator = None

        # Session tracking
        self.session_id = None
        self.video_path = None
        self.file_uri = None
        self.video_duration = 0.0
        self.clips = []
        self.clip_file_uris = []

    async def _upload_clip(self, client, clip, clip_index: int, total_clips: int) -> str:
        """
        Upload a single clip to Gemini and wait for it to be processed.
        
        This helper enables parallel uploads - can be called as asyncio.create_task()
        to upload multiple clips concurrently.
        
        Args:
            client: Gemini API client
            clip: VideoClip object to upload
            clip_index: Index of this clip (0-based)
            total_clips: Total number of clips
            
        Returns:
            File URI of the uploaded and processed clip
        """
        print(f"[UPLOAD] Starting upload for clip {clip_index + 1}/{total_clips}: {clip.path.name}")
        
        # Upload clip
        uploaded_file = await asyncio.to_thread(
            client.files.upload,
            file=str(clip.path)
        )
        file_name = uploaded_file.name
        
        # Wait for clip to be processed by Gemini
        max_retries = 60
        retry_count = 0
        
        while retry_count < max_retries:
            file_info = await asyncio.to_thread(
                client.files.get,
                name=file_name
            )
            
            if file_info.state.name == "ACTIVE":
                break
            
            await asyncio.sleep(1)
            retry_count += 1
        
        if retry_count == max_retries:
            raise TimeoutError(f"Clip {clip_index + 1} processing timeout")
        
        print(f"[UPLOAD] ✓ Clip {clip_index + 1}/{total_clips} ready: {uploaded_file.uri}")
        return uploaded_file.uri

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

            # Initialize StateManager for this session
            videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
            session_output_dir = videos_dir / 'streaming' / self.session_id
            session_output_dir.mkdir(exist_ok=True, parents=True)

            print(f"\n{'='*60}")
            print(f"[STREAMING PIPELINE] Initializing StateManager")
            print(f"Session ID: {self.session_id}")
            print(f"Output directory: {session_output_dir}")
            print(f"{'='*60}\n")

            # Create and initialize StateManager
            self.state_manager = StateManager(output_dir=session_output_dir)
            await self.state_manager.init_files()

            # Initialize components with StateManager
            self.event_detector = EventDetector(
                api_key=self.api_key,
                state_manager=self.state_manager,
                output_dir=session_output_dir
            )
            self.commentary_generator = CommentaryGenerator(
                api_key=self.api_key,
                state_manager=self.state_manager,
                output_dir=session_output_dir
            )

            yield {
                'type': 'status',
                'message': 'Starting video analysis...',
                'progress': 0
            }

            # Step 1: Prepare video
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

            # Step 2: Split video into clips
            yield {
                'type': 'status',
                'message': 'Splitting video into segments...',
                'progress': 10
            }

            splitter = VideoSplitter(ffmpeg_exe=self.video_processor.ffmpeg_exe)
            self.clips = await asyncio.to_thread(
                splitter.split_video,
                video_path=video_path_with_audio,
                duration_seconds=self.video_duration,
                interval_seconds=30
            )

            # Step 3 & 4: PARALLEL UPLOAD + PIPELINED PROCESSING
            # Start ALL uploads in parallel, process segments as soon as their upload completes
            # This significantly reduces time-to-first-chunk
            
            yield {
                'type': 'status',
                'message': f'Starting parallel upload of {len(self.clips)} segments...',
                'progress': 15
            }

            client = genai.Client(api_key=self.api_key)
            total_segments = len(self.clips)
            
            print(f"\n{'='*60}")
            print(f"[PARALLEL PIPELINE] Starting {total_segments} parallel uploads")
            print(f"{'='*60}\n")
            
            # Start ALL uploads in parallel as background tasks
            upload_tasks = {}
            for i, clip in enumerate(self.clips):
                upload_tasks[i] = asyncio.create_task(
                    self._upload_clip(client, clip, i, total_segments)
                )
            
            # Setup for processing
            streaming_dir = videos_dir / 'streaming' / self.session_id
            streaming_dir.mkdir(exist_ok=True, parents=True)
            chunk_index = 0
            
            # Process segments IN ORDER, but start processing as soon as upload is ready
            # While segment N is processing, segments N+1, N+2, etc. continue uploading
            for i, clip in enumerate(self.clips):
                # Wait for THIS segment's upload to complete (others continue in parallel)
                print(f"[PIPELINE] Waiting for segment {i + 1} upload...")
                file_uri = await upload_tasks[i]
                
                yield {
                    'type': 'status',
                    'message': f'Processing segment {i + 1}/{total_segments}...',
                    'progress': 15 + int((i / total_segments) * 80)
                }
                
                # Process this segment (other uploads continue in background)
                print(f"[PIPELINE] Processing segment {i + 1} while other uploads continue...")
                chunk_data = await self._process_segment_and_emit(
                    clip=clip,
                    file_uri=file_uri,
                    segment_index=i,
                    total_segments=total_segments,
                    video_path_with_audio=video_path_with_audio,
                    streaming_dir=streaming_dir
                )
                
                # EMIT chunk immediately so frontend can start playing
                if chunk_data:
                    yield {
                        'type': 'chunk_ready',
                        'index': chunk_data['index'],
                        'url': chunk_data['url'],
                        'start_time': chunk_data['start_time'],
                        'end_time': chunk_data['end_time'],
                        'progress': 15 + int(((i + 1) / total_segments) * 80)
                    }
                    chunk_index += 1
                    print(f"[PARALLEL PIPELINE] ✓ Segment {i + 1} EMITTED - user can watch now!")
            
            # Clean up temporary clip files
            print(f"\n[STREAMING] Cleaning up temporary clips...")
            splitter = VideoSplitter(ffmpeg_exe=self.video_processor.ffmpeg_exe)
            await asyncio.to_thread(splitter.cleanup_clips, self.clips)

            # Step 5: Create final concatenated video
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
            error_message = str(e)
            error_traceback = traceback.format_exc()
            print(f"\n{'='*60}")
            print(f"[STREAMING] ERROR OCCURRED")
            print(f"{'='*60}")
            print(f"Error: {error_message}")
            print(f"\nFull traceback:")
            print(error_traceback)
            print(f"{'='*60}\n")
            yield {
                'type': 'error',
                'message': error_message
            }

    async def _detect_events_streaming(self, event_queue: asyncio.Queue, sse_event_queue: asyncio.Queue):
        """
        Stage 1: Detect events from pre-split clips and push to queue.

        Args:
            event_queue: Queue to push detected events
            sse_event_queue: Queue to push SSE progress events
        """
        try:
            print(f"[STREAMING] Starting event detection...")
            print(f"[STREAMING] Using pre-split clips method (more reliable)")

            total_clips = len(self.clips)

            for i, (clip, file_uri) in enumerate(zip(self.clips, self.clip_file_uris), 1):
                print(f"[STREAMING] Analyzing clip {i}/{total_clips}: {seconds_to_time(clip.start_time)} - {seconds_to_time(clip.end_time)}")

                # Detect events for this clip
                events = await asyncio.to_thread(
                    self.event_detector.detect_events_for_interval,
                    file_uri=file_uri,
                    interval_start=clip.start_time,
                    interval_end=clip.end_time
                )

                # Save events to StateManager (happens inside detect_events_for_interval via _update_state)
                # StateManager handles all file I/O and state persistence
                await self.event_detector._update_state(events, clip.end_time)

                # Push to queue immediately (don't wait for other clips)
                await event_queue.put({
                    'interval': (clip.start_time, clip.end_time),
                    'events': events,
                    'interval_index': i - 1
                })

                print(f"[STREAMING] Pushed {len(events)} events from clip {i} to queue")

                # Emit SSE event for progress tracking
                await sse_event_queue.put({
                    'type': 'events_detected',
                    'count': len(events),
                    'interval': [clip.start_time, clip.end_time],
                    'interval_index': i - 1,
                    'total_intervals': total_clips
                })

            # Clean up temporary clip files
            print(f"[STREAMING] Cleaning up temporary clips...")
            splitter = VideoSplitter(ffmpeg_exe=self.video_processor.ffmpeg_exe)
            await asyncio.to_thread(splitter.cleanup_clips, self.clips)

            # Signal completion
            await event_queue.put(None)
            print(f"[STREAMING] Event detection completed - all events saved to StateManager")

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
                # NOTE: generate_commentary is now async and saves to StateManager internally
                try:
                    commentaries = await self.commentary_generator.generate_commentary(
                        events=[e.model_dump() for e in events],
                        video_duration=self.video_duration,  # Use FULL video duration, not interval end
                        use_streaming=False
                    )

                    # Push each commentary to queue immediately
                    # StateManager has already saved them via generate_commentary -> _save_commentaries
                    for commentary in commentaries:
                        await commentary_queue.put({
                            'commentary': commentary,
                            'interval_index': interval_index
                        })

                        print(f"[STREAMING] Pushed commentary to queue: {commentary.start_time} - {commentary.end_time}")

                        # Emit SSE event for progress tracking
                        await sse_event_queue.put({
                            'type': 'commentary_ready',
                            'text': commentary.commentary,
                            'start': commentary.start_time,
                            'end': commentary.end_time
                        })

                except Exception as e:
                    print(f"[STREAMING] Commentary generation failed for interval {interval}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue with next interval even if this one fails

                interval_index += 1

            # Signal completion
            await commentary_queue.put(None)
            await sse_event_queue.put(None)  # Signal SSE stream completion
            print(f"[STREAMING] Commentary generation completed - all commentaries saved to StateManager")

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
                commentary.commentary,
                commentary.speaker
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
        Stage 4: Create video chunks with TRUE STREAMING - emit as soon as ready.

        Uses a buffered streaming approach:
        - Buffer incoming audio (arrives out of order due to parallel TTS)
        - Emit chunks in chronological order as soon as they can be created
        - Don't wait for ALL audio - emit incrementally for real-time playback

        Args:
            audio_queue: Input queue with audio data
            chunk_queue: Output queue for video chunks
            video_path: Path to original video
        """
        import heapq
        
        try:
            print(f"[STREAMING] Starting video chunk creation (TRUE STREAMING MODE)...")

            # Create output directory for chunks
            videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
            streaming_dir = videos_dir / 'streaming' / self.session_id
            streaming_dir.mkdir(exist_ok=True, parents=True)

            # Buffer for out-of-order audio arrivals
            # Using a min-heap sorted by start_time for efficient retrieval
            audio_buffer = []  # heap of (start_time, audio_data)
            
            chunk_index = 0
            chunk_start = 0.0  # First chunk always starts at video beginning
            audio_complete = False
            total_emitted = 0

            async def try_emit_next_chunk():
                """Try to emit the next chunk if we have the audio for it."""
                nonlocal chunk_index, chunk_start, total_emitted
                
                if not audio_buffer:
                    return False
                
                # Peek at the earliest audio in buffer
                earliest_start, audio_data = audio_buffer[0]
                commentary = audio_data['commentary']
                audio_base64 = audio_data['audio_base64']
                chunk_end = parse_time_to_seconds(commentary.end_time)
                
                # Check if this audio is for our current chunk position
                # Allow some tolerance for timing
                if earliest_start <= chunk_start + 5.0:  # 5 second tolerance
                    # Pop from buffer
                    heapq.heappop(audio_buffer)
                    
                    # Validate chunk duration
                    chunk_duration = chunk_end - chunk_start
                    if chunk_duration < 0.1:
                        print(f"[STREAMING] Skipping chunk {chunk_index}: duration too small ({chunk_duration:.2f}s)")
                        return True  # Continue trying
                    
                    # Clamp chunk_end to video duration
                    if chunk_end > self.video_duration:
                        chunk_end = self.video_duration
                    
                    print(f"[STREAMING] Creating chunk {chunk_index}: {seconds_to_time(chunk_start)} - {seconds_to_time(chunk_end)} (STREAMING)")
                    
                    try:
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
                        
                        chunk_url = f"/videos/streaming/{self.session_id}/chunk_{chunk_index}.mp4"
                        
                        await chunk_queue.put({
                            'path': chunk_path,
                            'url': chunk_url,
                            'index': chunk_index,
                            'start_time': seconds_to_time(chunk_start),
                            'end_time': seconds_to_time(chunk_end)
                        })
                        
                        print(f"[STREAMING] ✓ Chunk {chunk_index} EMITTED: {chunk_url}")
                        total_emitted += 1
                        
                        chunk_start = chunk_end
                        chunk_index += 1
                        return True
                        
                    except Exception as e:
                        print(f"[STREAMING] Chunk creation failed for index {chunk_index}: {e}")
                        print(traceback.format_exc())
                        return True  # Continue trying with next
                
                return False

            # Main streaming loop - process audio as it arrives
            while not audio_complete or audio_buffer:
                # Try to emit any chunks we can with current buffer
                while await try_emit_next_chunk():
                    pass
                
                if audio_complete and not audio_buffer:
                    break
                
                # Wait for next audio with timeout
                try:
                    audio_data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    
                    if audio_data is None:
                        print(f"[STREAMING] Audio queue complete, {len(audio_buffer)} items in buffer")
                        audio_complete = True
                    else:
                        # Add to buffer sorted by start_time
                        commentary = audio_data['commentary']
                        start_time = parse_time_to_seconds(commentary.start_time)
                        heapq.heappush(audio_buffer, (start_time, audio_data))
                        print(f"[STREAMING] Buffered audio for {commentary.start_time} (buffer size: {len(audio_buffer)})")
                        
                except asyncio.TimeoutError:
                    # Timeout - just try to emit again
                    continue

            # Create final chunk from last commentary end to video end
            final_chunk_duration = self.video_duration - chunk_start
            if chunk_start < self.video_duration and final_chunk_duration >= 0.1:
                print(f"[STREAMING] Creating final chunk {chunk_index}: {seconds_to_time(chunk_start)} - {seconds_to_time(self.video_duration)}")

                try:
                    chunk_path = await asyncio.to_thread(
                        self._create_single_chunk,
                        video_path,
                        chunk_start,
                        self.video_duration,
                        None,
                        None,
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

                    print(f"[STREAMING] ✓ Final chunk {chunk_index} EMITTED")
                    chunk_index += 1

                except Exception as e:
                    print(f"[STREAMING] Final chunk creation failed: {e}")
                    print(traceback.format_exc())

            # Signal completion
            await chunk_queue.put(None)
            print(f"[STREAMING] Video chunk creation completed ({chunk_index} chunks emitted)")

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

    def _create_single_chunk_multi_audio(
        self,
        video_path: Path,
        chunk_start: float,
        chunk_end: float,
        audio_data_list: list,
        chunk_index: int,
        output_dir: Path
    ) -> Path:
        """
        Create a single video chunk with MULTIPLE audio overlays.
        
        Each commentary audio is overlaid at its correct timestamp using
        FFmpeg's filter_complex to mix all audio streams together.
        
        This is a SYNCHRONOUS method that will be run in a thread.
        
        Args:
            video_path: Path to original video
            chunk_start: Start time in seconds (relative to original video)
            chunk_end: End time in seconds (relative to original video)
            audio_data_list: List of {'commentary': obj, 'audio_base64': str}
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
        
        if not audio_data_list:
            # No commentary - just create video segment
            print(f"[CHUNK {chunk_index}] No audio overlays, creating video-only chunk")
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
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")
            return chunk_path
        
        # Create chunk with multiple audio overlays
        print(f"[CHUNK {chunk_index}] Creating chunk with {len(audio_data_list)} audio overlays")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Save all audio files to temp directory
            audio_files = []
            delays_ms = []
            
            for i, audio_data in enumerate(audio_data_list):
                commentary = audio_data['commentary']
                audio_base64 = audio_data['audio_base64']
                
                # Save audio file
                audio_file = temp_path / f"commentary_{i}.mp3"
                audio_bytes = base64.b64decode(audio_base64)
                audio_file.write_bytes(audio_bytes)
                audio_files.append(audio_file)
                
                # Calculate delay relative to chunk start
                commentary_start = parse_time_to_seconds(commentary.start_time)
                delay_from_chunk_start = commentary_start - chunk_start
                delay_ms = max(0, int(delay_from_chunk_start * 1000))  # Ensure non-negative
                delays_ms.append(delay_ms)
                
                print(f"[CHUNK {chunk_index}] Audio {i}: {commentary.start_time} -> delay={delay_ms}ms")
            
            # Build FFmpeg command with filter_complex for multiple audios
            # Input: video + all audio files
            cmd = [self.video_processor.ffmpeg_exe, '-y']
            cmd.extend(['-ss', str(chunk_start), '-to', str(chunk_end)])
            cmd.extend(['-i', str(video_path)])
            
            for audio_file in audio_files:
                cmd.extend(['-i', str(audio_file)])
            
            # Build filter_complex string
            # [0:a] is original audio, [1:a], [2:a], etc are commentary audios
            filter_parts = ['[0:a]volume=0.2[orig]']
            mix_inputs = ['[orig]']
            
            for i in range(len(audio_files)):
                delay = delays_ms[i]
                filter_parts.append(f'[{i+1}:a]adelay={delay}|{delay}[c{i}]')
                mix_inputs.append(f'[c{i}]')
            
            # Mix all inputs together
            mix_input_str = ''.join(mix_inputs)
            num_inputs = len(audio_files) + 1  # original + all commentaries
            filter_parts.append(f'{mix_input_str}amix=inputs={num_inputs}:duration=first[aout]')
            
            filter_complex = ';'.join(filter_parts)
            
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '0:v',
                '-map', '[aout]',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-c:a', 'aac',
                '-ar', '44100',
                '-b:a', '192k',
                '-movflags', '+faststart',
                str(chunk_path)
            ])
            
            print(f"[CHUNK {chunk_index}] Running FFmpeg with {len(audio_files)} audio tracks...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                print(f"[CHUNK {chunk_index}] FFmpeg error: {result.stderr}")
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        print(f"[CHUNK {chunk_index}] Successfully created with {len(audio_files)} overlays")
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

    async def _process_segment_and_emit(
        self,
        clip: VideoClip,
        file_uri: str,
        segment_index: int,
        total_segments: int,
        video_path_with_audio: Path,
        streaming_dir: Path
    ) -> Dict[str, Any]:
        """
        Process ONE segment completely through the entire pipeline and return chunk data.
        
        This enables TRUE STREAMING: each segment is fully processed and emitted
        before starting the next, so users can watch while processing continues.
        
        Pipeline for this segment:
        1. Detect events
        2. Generate commentary
        3. Generate TTS audio
        4. Create video chunk with audio overlay
        5. Return chunk data for immediate emission
        
        Args:
            clip: The video clip to process
            file_uri: Gemini file URI for this clip
            segment_index: Index of this segment (0-based)
            total_segments: Total number of segments
            video_path_with_audio: Path to full video with audio
            streaming_dir: Directory to save chunks
            
        Returns:
            Chunk data dict with path, url, index, start_time, end_time
        """
        print(f"\n{'='*60}")
        print(f"[SEGMENT {segment_index + 1}/{total_segments}] Processing {seconds_to_time(clip.start_time)} - {seconds_to_time(clip.end_time)}")
        print(f"{'='*60}")
        
        # Step 1: Detect events for this segment
        print(f"[SEGMENT {segment_index + 1}] Detecting events...")
        events = await asyncio.to_thread(
            self.event_detector.detect_events_for_interval,
            file_uri=file_uri,
            interval_start=clip.start_time,
            interval_end=clip.end_time
        )
        await self.event_detector._update_state(events, clip.end_time)
        print(f"[SEGMENT {segment_index + 1}] Detected {len(events)} events")
        
        # Step 2: Generate commentary for these events
        if not events:
            print(f"[SEGMENT {segment_index + 1}] No events, creating chunk without commentary")
            commentaries = []
        else:
            print(f"[SEGMENT {segment_index + 1}] Generating commentary...")
            try:
                commentaries = await self.commentary_generator.generate_commentary(
                    events=[e.model_dump() for e in events],
                    video_duration=self.video_duration,
                    use_streaming=False
                )
                print(f"[SEGMENT {segment_index + 1}] Generated {len(commentaries)} commentary segments")
            except Exception as e:
                print(f"[SEGMENT {segment_index + 1}] Commentary generation failed: {e}")
                commentaries = []
        
        # Step 3: Generate TTS for all commentaries in this segment
        audio_data_list = []
        if commentaries and self.tts_generator:
            print(f"[SEGMENT {segment_index + 1}] Generating TTS audio...")
            for commentary in commentaries:
                try:
                    audio_base64 = await asyncio.to_thread(
                        self.tts_generator.generate_audio,
                        commentary.commentary,
                        getattr(commentary, 'speaker', None)
                    )
                    audio_data_list.append({
                        'commentary': commentary,
                        'audio_base64': audio_base64
                    })
                    print(f"[SEGMENT {segment_index + 1}] TTS completed for {commentary.start_time}")
                except Exception as e:
                    print(f"[SEGMENT {segment_index + 1}] TTS failed: {e}")
                    audio_data_list.append({
                        'commentary': commentary,
                        'audio_base64': None
                    })
        
        # Step 4: Create video chunk for this segment
        chunk_start = clip.start_time
        chunk_end = clip.end_time
        
        # Filter commentaries to only those within THIS segment's time range
        # This is critical - commentaries may have timestamps outside segment boundaries
        segment_audio_list = []
        if audio_data_list:
            for audio_data in audio_data_list:
                if audio_data['audio_base64']:
                    commentary_start = parse_time_to_seconds(audio_data['commentary'].start_time)
                    # Include commentary if it starts within this segment
                    if chunk_start <= commentary_start < chunk_end:
                        segment_audio_list.append(audio_data)
                        print(f"[SEGMENT {segment_index + 1}] Including commentary at {audio_data['commentary'].start_time}")
                    else:
                        print(f"[SEGMENT {segment_index + 1}] Skipping commentary at {audio_data['commentary'].start_time} (outside segment {chunk_start}-{chunk_end})")
            
            # Sort by start time for proper overlay order
            segment_audio_list.sort(key=lambda x: parse_time_to_seconds(x['commentary'].start_time))
        
        print(f"[SEGMENT {segment_index + 1}] Creating video chunk with {len(segment_audio_list)} audio overlays...")
        try:
            chunk_path = await asyncio.to_thread(
                self._create_single_chunk_multi_audio,
                video_path_with_audio,
                chunk_start,
                chunk_end,
                segment_audio_list,  # Pass ALL filtered audios
                segment_index,
                streaming_dir
            )
            
            chunk_url = f"/videos/streaming/{self.session_id}/chunk_{segment_index}.mp4"
            
            print(f"[SEGMENT {segment_index + 1}] ✓ CHUNK READY: {chunk_url}")
            
            return {
                'path': chunk_path,
                'url': chunk_url,
                'index': segment_index,
                'start_time': seconds_to_time(chunk_start),
                'end_time': seconds_to_time(chunk_end)
            }
            
        except Exception as e:
            print(f"[SEGMENT {segment_index + 1}] Chunk creation failed: {e}")
            traceback.print_exc()
            return None

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
