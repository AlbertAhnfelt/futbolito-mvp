# REAL_TIME_PLAN.md - Streaming Video Commentary System

## Executive Summary

Transform the current **sequential batch pipeline** into a **real-time streaming pipeline** that delivers video chunks to users as soon as commentary is generated, enabling playback to start while generation continues.

**Current bottleneck:** User waits ~67 seconds for a 133-second video
**Target improvement:** First chunk plays in ~18 seconds (3.7x faster)

---

## System Architecture Overview

### Current Pipeline (Sequential)
```
Video Upload (10s)
  → Event Detection [ALL intervals] (40s)
    → Commentary Generation [ALL events] (10s)
      → TTS [ALL segments] (12s)
        → Video Assembly [ALL chunks] (5s)
          → Return final video (77s total)
```

### New Pipeline (Streaming)
```
Video Upload (10s)
  ↓
  ├─→ Event Detection [interval 0-30s] (8s)
  │     ↓
  │     └─→ Commentary Gen [batch 1] (3s)
  │           ↓
  │           └─→ TTS [segment 1] (3s)
  │                 ↓
  │                 └─→ Chunk Creation (2s) → SSE: chunk_0.mp4 ✓ (18s - USER STARTS WATCHING)
  │
  ├─→ Event Detection [interval 30-60s] (8s)
  │     ↓
  │     └─→ Commentary Gen [batch 2] (3s) → TTS → Chunk → SSE: chunk_1.mp4 ✓
  │
  └─→ [continues for remaining intervals...]
```

---

## Core Technical Solution

### 1. Producer-Consumer Pattern with Async Queues

```python
# Pipeline stages connected by queues
Event Queue → Commentary Queue → Audio Queue → Chunk Queue → SSE Stream

# Each stage runs concurrently
asyncio.gather(
    detect_events_streaming(event_queue),           # Producer 1
    generate_commentary_streaming(commentary_queue), # Consumer 1 + Producer 2
    generate_audio_parallel(audio_queue),           # Consumer 2 + Producer 3
    create_video_chunks(chunk_queue),               # Consumer 3 + Producer 4
    emit_sse_events(chunk_queue)                    # Consumer 4 (to client)
)
```

**Why this works:**
- Each stage processes independently
- No waiting for entire pipeline to complete
- Natural backpressure handling via queues
- Failures in one stage don't block others

---

## Solutions to Key Problems

### Problem 1: How to stream video chunks to user?

**Solution: Progressive MP4 Segments via SSE**

```
Backend generates:
/videos/streaming/session_abc123/
  ├── chunk_0.mp4  (original video 00:23-00:35 + commentary audio)
  ├── chunk_1.mp4  (original video 00:47-00:58 + commentary audio)
  ├── chunk_2.mp4  (original video 01:15-01:28 + commentary audio)
  └── chunk_3.mp4  (original video 01:52-02:07 + commentary audio)

SSE events sent to frontend:
data: {"type": "chunk_ready", "url": "/videos/streaming/session_abc123/chunk_0.mp4", "index": 0}
data: {"type": "chunk_ready", "url": "/videos/streaming/session_abc123/chunk_1.mp4", "index": 1}
data: {"type": "chunk_ready", "url": "/videos/streaming/session_abc123/chunk_2.mp4", "index": 2}
data: {"type": "complete", "final_video": "/videos/generated-videos/commentary_final.mp4"}

Frontend plays:
- Option A: Sequential playback (play chunk_0, then chunk_1, etc.)
- Option B: Client-side concatenation (load all, merge, play)
- Option C: Hybrid (play first chunk, load rest in background)
```

**Technical details:**
- Each chunk is a complete, playable MP4
- Use `-movflags +faststart` for immediate playback
- Chunks have identical encoding params (enables seamless concat)

---

### Problem 2: Ensure TEXT → AUDIO → ADD per segment (not batch)

**Solution: Async Queue Pipeline with Immediate Processing**

#### Stage 1: Event Detection (Streaming)
```python
async def detect_events_streaming(event_queue: asyncio.Queue):
    """Detect events and push to queue after EACH 30s interval"""
    intervals = [(0,30), (30,60), (60,90), ...]

    for interval in intervals:
        # Detect events for this 30s chunk
        events = await gemini_detect_events(interval)

        # Push immediately (don't wait for other intervals)
        await event_queue.put({
            'interval': interval,
            'events': events
        })

    await event_queue.put(None)  # Signal completion
```

#### Stage 2: Commentary Generation (Per-Interval)
```python
async def generate_commentary_streaming(event_queue: asyncio.Queue,
                                       commentary_queue: asyncio.Queue):
    """Generate commentary for EACH event batch immediately"""
    while True:
        event_batch = await event_queue.get()
        if event_batch is None:
            break

        # Generate commentary for just these events
        commentaries = await gemini_generate_commentary(event_batch['events'])

        # Push each commentary immediately
        for commentary in commentaries:
            await commentary_queue.put(commentary)

    await commentary_queue.put(None)
```

**Alternative:** Wait for all events, use Gemini streaming API
- Trade-off: Better commentary quality vs slower first chunk
- Implementation: Use `generate_content_stream()` and yield as received

#### Stage 3: TTS Generation (Parallel)
```python
async def generate_audio_parallel(commentary_queue: asyncio.Queue,
                                  audio_queue: asyncio.Queue):
    """Process multiple TTS requests concurrently"""
    tasks = set()

    while True:
        commentary = await commentary_queue.get()
        if commentary is None:
            break

        # Create task for this TTS request
        task = asyncio.create_task(
            generate_single_audio(commentary, audio_queue)
        )
        tasks.add(task)

        # Limit concurrency (ElevenLabs rate limits)
        if len(tasks) >= 5:
            done, tasks = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

    await asyncio.gather(*tasks)  # Wait for remaining
    await audio_queue.put(None)

async def generate_single_audio(commentary, audio_queue):
    """Generate audio and push to queue when ready"""
    audio_bytes = await elevenlabs_tts(commentary.text)

    await audio_queue.put({
        'commentary': commentary,
        'audio_bytes': audio_bytes
    })
```

#### Stage 4: Chunk Creation (Sequential)
```python
async def create_video_chunks(audio_queue: asyncio.Queue,
                             chunk_queue: asyncio.Queue):
    """Create video chunk for EACH commentary immediately"""
    chunk_index = 0

    while True:
        audio_data = await audio_queue.get()
        if audio_data is None:
            break

        # Create chunk immediately
        chunk_path = await create_single_chunk(
            original_video=VIDEO_PATH,
            commentary=audio_data['commentary'],
            audio_bytes=audio_data['audio_bytes'],
            index=chunk_index
        )

        await chunk_queue.put({
            'path': chunk_path,
            'index': chunk_index
        })
        chunk_index += 1

    await chunk_queue.put(None)
```

**Flow guarantee:**
```
Commentary 1 text ready → TTS starts for Commentary 1
Commentary 1 audio ready → Chunk 1 creation starts
Chunk 1 ready → SSE sent to client

(Meanwhile, Commentary 2 might be generating in parallel)
```

---

### Problem 3: Ensure smooth audio flow across chunks

**Solution: Precise Time Boundaries + Consistent Encoding**

#### Chunk Creation with Exact Time Extraction
```bash
# Each chunk extracts exact time segment from original video
ffmpeg -ss {start_time} -to {end_time} -i original.mp4 \
  -i commentary_audio.mp3 \
  -filter_complex "
    [0:a]volume=0.2[orig_reduced];
    [1:a]adelay=1000|1000[comm_delayed];
    [orig_reduced][comm_delayed]amix=inputs=2:duration=first[audio_out]
  " \
  -map 0:v -map [audio_out] \
  -c:v libx264 -preset ultrafast \
  -c:a aac -ar 44100 -b:a 192k \
  -movflags +faststart \
  chunk_{index}.mp4
```

**Key parameters for smooth concatenation:**
- `-ar 44100`: Same audio sample rate across ALL chunks
- `-b:a 192k`: Same audio bitrate
- `-c:a aac`: Same audio codec
- Video codec can vary (will re-encode on final concat if needed)

#### Why This Creates Smooth Playback

**Chunk boundaries align with natural gaps:**
```
Original video timeline:
|─────────────────────────────────────────────────────|
0s      23s   35s    47s   58s      1:15   1:28     2:07

Chunk 0: [00:23 ────→ 00:35]  (12s chunk)
         Background audio (20%) + Commentary 1

Gap:     [00:35 ────→ 00:47]  (12s gap - original audio only)

Chunk 1: [00:47 ────→ 00:58]  (11s chunk)
         Background audio (20%) + Commentary 2

Gap:     [00:58 ────→ 01:15]  (17s gap - original audio only)

Chunk 2: [01:15 ────→ 01:28]  (13s chunk)
         Background audio (20%) + Commentary 3
```

**Smooth playback because:**
1. Each chunk contains continuous original audio (reduced to 20%)
2. Gaps between chunks play original audio at 100% (no chunks for those sections)
3. No audio dropouts - original audio is never cut
4. Commentary overlays at precise times with 1s delay

#### Final Concatenation (Optional Background Job)

```bash
# Create concat list
echo "file 'chunk_0.mp4'" > list.txt
echo "file 'chunk_1.mp4'" >> list.txt
echo "file 'chunk_2.mp4'" >> list.txt

# Lossless merge (near-instant, no re-encoding)
ffmpeg -f concat -safe 0 -i list.txt -c copy final.mp4
```

**When to run:**
- After all chunks sent to client
- Background task (user already watching)
- Creates single file for easier sharing/download

---

## Implementation Details

### File Structure

```
backend/src/video_analysis/
├── streaming_pipeline.py          # NEW: Async orchestration
├── route.py                        # MODIFY: Add SSE endpoint
├── controller.py                   # MODIFY: Call streaming pipeline
│
├── analysis/
│   └── event_detector.py          # MODIFY: Make async, yield to queue
│
├── commentary/
│   └── commentary_generator.py    # MODIFY: Per-interval generation
│
├── audio/
│   └── tts_generator.py           # MODIFY: Async with parallel support
│
└── video/
    └── video_processor.py         # MODIFY: Add create_single_chunk()
```

### SSE Endpoint

```python
# route.py
from fastapi.responses import StreamingResponse

@router.get("/analyze-stream/{filename}")
async def analyze_video_stream(filename: str):
    """Stream video generation progress via SSE"""

    async def event_generator():
        try:
            async for event in streaming_pipeline(filename):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
```

### Event Types Sent to Frontend

```python
# Progress events
{"type": "status", "message": "Uploading video...", "progress": 10}
{"type": "status", "message": "Analyzing events (interval 1/5)", "progress": 30}
{"type": "status", "message": "Generating commentary...", "progress": 50}

# Data events
{"type": "events_detected", "count": 12, "interval": [0, 30]}
{"type": "commentary_ready", "index": 0, "text": "...", "start": "00:23", "end": "00:35"}

# Chunk events (most important)
{"type": "chunk_ready", "index": 0, "url": "/videos/streaming/abc123/chunk_0.mp4", "start": "00:23", "end": "00:35"}
{"type": "chunk_ready", "index": 1, "url": "/videos/streaming/abc123/chunk_1.mp4", "start": "00:47", "end": "00:58"}

# Completion events
{"type": "complete", "chunks": 4, "final_video": "/videos/generated-videos/commentary_20250116_143022.mp4"}
{"type": "error", "message": "TTS failed for segment 2, skipping..."}
```

---

## Performance Analysis

### Current System (133-second video)
```
Video Upload:        10s  ████████
Event Detection:     40s  ████████████████████████████
Commentary Gen:      10s  ████████
TTS Generation:      12s  ██████████
Video Assembly:       5s  ████
─────────────────────────────────────────────
Total:               77s  (user sees nothing)
First playback:      77s  ⚠️
```

### New System (133-second video)
```
Video Upload:        10s  ████████
Interval 1 Events:    8s  ██████
  → Commentary:       3s  ██
    → TTS:            3s  ██
      → Chunk 0:      2s  █  ✓ CHUNK 0 READY (18s)
Interval 2 Events:    8s  ██████
  → Commentary:       3s  ██
    → TTS:            3s  ██
      → Chunk 1:      2s  █  ✓ CHUNK 1 READY (26s)
[continues...]
─────────────────────────────────────────────
Total:               45s  (all chunks ready)
First playback:      18s  ✓ 4.3x faster!
```

**Key improvements:**
- **Perceived latency:** 77s → 18s (76% reduction)
- **Total generation time:** 77s → 45s (42% reduction)
- **Parallel processing:** TTS requests run concurrently
- **User experience:** Progressive playback vs. wait-for-all

---

## Error Handling Strategy

### 1. TTS Failures
```python
try:
    audio = await generate_audio(commentary)
except ElevenLabsQuotaError:
    # Skip this commentary, log warning, continue pipeline
    logger.warning(f"Skipping commentary {index}: quota exceeded")
    await audio_queue.put({'commentary': commentary, 'audio_bytes': None})
    # Frontend receives skip event
    yield {"type": "warning", "message": "Commentary skipped due to quota"}
```

### 2. Event Detection Failures
```python
try:
    events = await detect_events(interval)
except GeminiAPIError as e:
    # Retry with exponential backoff
    events = await retry_with_backoff(detect_events, interval)
    if not events:
        # Continue with empty events for this interval
        yield {"type": "warning", "message": f"No events detected for interval {interval}"}
```

### 3. Chunk Creation Failures
```python
try:
    chunk = await create_chunk(commentary, audio)
except FFmpegError as e:
    # Skip chunk, but continue pipeline
    logger.error(f"Chunk {index} failed: {e}")
    yield {"type": "error", "message": f"Chunk {index} failed, continuing..."}
    # Don't break the stream
```

**Philosophy:** Graceful degradation over complete failure
- Missing commentary → video plays with gap
- Failed TTS → skip that segment
- Chunk error → continue with remaining chunks

---

## Optimization Opportunities

### Phase 1: Basic Streaming (Implement First)
- Async pipeline with queues
- Sequential chunk creation
- Basic SSE delivery

### Phase 2: Parallelization
- Parallel TTS (5 concurrent requests)
- Parallel event detection (multiple intervals)
- Background final video concatenation

### Phase 3: Advanced Optimizations
**Video encoding optimization:**
```python
# For sections without commentary, use -c:v copy (instant)
if has_commentary:
    encode_with_audio_overlay()  # Re-encode required
else:
    copy_video_segment()  # Fast extraction
```

**Smart buffering:**
```python
# Wait for 2 chunks before sending first (smooth playback)
chunk_buffer = []
while len(chunk_buffer) < 2:
    chunk = await chunk_queue.get()
    chunk_buffer.append(chunk)

# Then stream all
for chunk in chunk_buffer:
    yield chunk_event
```

**Caching:**
```python
# Cache event detection for same video
cache_key = f"events_{video_hash}_{interval}"
if cached := redis.get(cache_key):
    return cached_events
```

---

## Testing Strategy

### Unit Tests
- Test each pipeline stage independently
- Mock API calls (Gemini, ElevenLabs)
- Verify queue behavior under failures

### Integration Tests
- Test full pipeline with sample video
- Verify chunk concatenation produces valid MP4
- Test error scenarios (API failures, quota limits)

### Performance Tests
- Measure time-to-first-chunk
- Verify parallel TTS efficiency
- Test with videos of varying lengths (30s, 2min, 5min)

### User Acceptance
- Frontend plays chunks smoothly
- No audio glitches at chunk boundaries
- Progress indicators update correctly

---

## Rollout Plan

### Stage 1: Backend Streaming Infrastructure
1. Create `streaming_pipeline.py` with queue orchestration
2. Add SSE endpoint to `route.py`
3. Make event detector async and queue-aware
4. Test event detection streaming

### Stage 2: Commentary & TTS Streaming
5. Update commentary generator for per-interval generation
6. Implement parallel TTS with concurrency limits
7. Test commentary → audio pipeline

### Stage 3: Video Chunk Creation
8. Implement `create_single_chunk()` in video processor
9. Test chunk creation with sample commentaries
10. Verify chunk concatenation produces valid output

### Stage 4: Integration & Testing
11. Connect all pipeline stages
12. Frontend integration (SSE client, video player)
13. End-to-end testing with real videos

### Stage 5: Optimization & Polish
14. Add error handling and retries
15. Implement smart buffering
16. Performance optimization
17. Production deployment

---

## Risk Mitigation

### Risk 1: Chunk Concatenation Issues
**Mitigation:**
- Use identical encoding params across chunks
- Test concatenation extensively
- Fallback: Re-encode final video if concat fails

### Risk 2: ElevenLabs Rate Limits
**Mitigation:**
- Limit parallel requests to 5
- Implement exponential backoff
- Cache TTS results for duplicate text

### Risk 3: Increased Server Load
**Mitigation:**
- Limit concurrent streaming sessions (e.g., max 3)
- Use queue-based job system (Celery/RQ)
- Monitor resource usage, scale horizontally if needed

### Risk 4: Disk Space for Chunks
**Mitigation:**
- Clean up chunks after final concatenation
- Implement TTL for streaming sessions (1 hour)
- Monitor disk usage, alert if low

---

## Success Metrics

**Primary:**
- Time to first chunk: < 20 seconds
- Total generation time: < 50% of current

**Secondary:**
- Chunk concatenation success rate: > 99%
- Audio quality: No perceptible glitches
- Error recovery: Pipeline continues despite individual failures

**User experience:**
- Can start watching while generation continues
- Progress indicators update in real-time
- Smooth playback across chunk boundaries

---

## Future Enhancements

1. **HLS Support:** Generate .m3u8 playlist for native browser streaming
2. **Multi-quality:** Generate 720p + 1080p streams simultaneously
3. **Live streaming:** Real-time commentary during live matches
4. **Caching layer:** Redis cache for events/commentary of same video
5. **CDN integration:** Serve chunks from CDN for global delivery

---

## Technical References

### FFmpeg Resources
- [Concatenation docs](https://trac.ffmpeg.org/wiki/Concatenate)
- [Streaming docs](https://trac.ffmpeg.org/wiki/StreamingGuide)
- [Fast start flag](https://trac.ffmpeg.org/wiki/Encode/H.264#faststartforwebvideo)

### Python Async
- [asyncio queues](https://docs.python.org/3/library/asyncio-queue.html)
- [FastAPI SSE](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)

### Industry Patterns
- YouTube's adaptive streaming architecture
- Twitch's live transcoding pipeline
- Netflix's video encoding optimizations

---

*Last updated: 2025-01-16*
