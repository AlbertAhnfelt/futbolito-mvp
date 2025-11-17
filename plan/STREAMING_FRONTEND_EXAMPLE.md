# Frontend Implementation Guide for Streaming Video Commentary

This document provides example code for consuming the real-time streaming API.

## Overview

The streaming API delivers video chunks via Server-Sent Events (SSE) as soon as commentary is generated, enabling progressive playback while generation continues in the background.

## API Endpoint

```
GET /analyze-stream/{filename}
```

## Event Types

The SSE stream sends the following event types:

### 1. Status Events
Progress updates during processing:
```json
{
  "type": "status",
  "message": "Uploading video to analysis service...",
  "progress": 10
}
```

### 2. Chunk Ready Events
Video chunks ready for playback:
```json
{
  "type": "chunk_ready",
  "index": 0,
  "url": "/videos/streaming/session_20250116_143022/chunk_0.mp4",
  "start_time": "00:00:23",
  "end_time": "00:00:35",
  "progress": 25
}
```

### 3. Complete Event
All processing finished:
```json
{
  "type": "complete",
  "chunks": 4,
  "final_video": "commentary_20250116_143022.mp4",
  "progress": 100
}
```

### 4. Error Event
Processing error:
```json
{
  "type": "error",
  "message": "Error description"
}
```

---

## Frontend Implementation

### Option A: Sequential Playback (Recommended)

Play each chunk immediately as it arrives, then automatically play the next chunk.

```javascript
// React example with sequential playback
import React, { useState, useEffect, useRef } from 'react';

function StreamingVideoPlayer({ filename }) {
  const [chunks, setChunks] = useState([]);
  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const videoRef = useRef(null);

  useEffect(() => {
    // Create EventSource for SSE
    const eventSource = new EventSource(`/api/analyze-stream/${filename}`);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          setStatus(data.message);
          setProgress(data.progress);
          break;

        case 'chunk_ready':
          console.log('Chunk ready:', data.index, data.url);

          // Add chunk to list
          setChunks(prev => [...prev, {
            index: data.index,
            url: data.url,
            startTime: data.start_time,
            endTime: data.end_time
          }]);

          // If this is the first chunk, start playing
          if (data.index === 0 && videoRef.current) {
            videoRef.current.src = data.url;
            videoRef.current.play();
          }

          setProgress(data.progress);
          break;

        case 'complete':
          console.log('Processing complete:', data.chunks, 'chunks');
          setIsComplete(true);
          setProgress(100);
          setStatus('Complete!');
          eventSource.close();
          break;

        case 'error':
          console.error('Processing error:', data.message);
          setStatus(`Error: ${data.message}`);
          eventSource.close();
          break;
      }
    };

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [filename]);

  // Handle video ended - play next chunk
  const handleVideoEnded = () => {
    const nextIndex = currentChunkIndex + 1;

    if (nextIndex < chunks.length) {
      // Play next chunk
      const nextChunk = chunks[nextIndex];
      videoRef.current.src = nextChunk.url;
      videoRef.current.play();
      setCurrentChunkIndex(nextIndex);
    } else if (isComplete) {
      // All chunks played and processing complete
      console.log('Playback complete');
    } else {
      // Wait for next chunk to arrive
      console.log('Waiting for next chunk...');
    }
  };

  return (
    <div>
      <div className="progress-bar">
        <div className="progress" style={{ width: `${progress}%` }} />
      </div>

      <div className="status">{status}</div>

      <video
        ref={videoRef}
        controls
        onEnded={handleVideoEnded}
        style={{ width: '100%', maxWidth: '800px' }}
      />

      <div className="chunk-info">
        Playing chunk {currentChunkIndex + 1} of {chunks.length}
        {!isComplete && ' (more chunks loading...)'}
      </div>

      <div className="chunk-list">
        <h4>Chunks ({chunks.length}):</h4>
        {chunks.map(chunk => (
          <div key={chunk.index}>
            Chunk {chunk.index}: {chunk.startTime} - {chunk.endTime}
          </div>
        ))}
      </div>
    </div>
  );
}

export default StreamingVideoPlayer;
```

---

### Option B: Client-Side Concatenation

Load all chunks, concatenate in browser, then play as single video.

```javascript
// Using MediaSource API for seamless concatenation
import React, { useState, useEffect, useRef } from 'react';

function ConcatenatedStreamingPlayer({ filename }) {
  const [chunks, setChunks] = useState([]);
  const [isComplete, setIsComplete] = useState(false);
  const [progress, setProgress] = useState(0);
  const videoRef = useRef(null);
  const mediaSourceRef = useRef(null);
  const sourceBufferRef = useRef(null);

  useEffect(() => {
    const eventSource = new EventSource(`/api/analyze-stream/${filename}`);

    // Initialize MediaSource
    const mediaSource = new MediaSource();
    mediaSourceRef.current = mediaSource;
    videoRef.current.src = URL.createObjectURL(mediaSource);

    mediaSource.addEventListener('sourceopen', () => {
      const sourceBuffer = mediaSource.addSourceBuffer('video/mp4; codecs="avc1.64001f,mp4a.40.2"');
      sourceBufferRef.current = sourceBuffer;
    });

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'chunk_ready':
          console.log('Chunk ready:', data.index, data.url);

          // Fetch chunk and append to MediaSource
          fetch(data.url)
            .then(res => res.arrayBuffer())
            .then(buffer => {
              if (sourceBufferRef.current && !sourceBufferRef.current.updating) {
                sourceBufferRef.current.appendBuffer(buffer);
              }

              // Start playing after first chunk
              if (data.index === 0) {
                videoRef.current.play();
              }
            });

          setChunks(prev => [...prev, data]);
          setProgress(data.progress);
          break;

        case 'complete':
          console.log('Processing complete');
          setIsComplete(true);
          setProgress(100);

          // End MediaSource stream
          if (mediaSourceRef.current.readyState === 'open') {
            mediaSourceRef.current.endOfStream();
          }

          eventSource.close();
          break;

        case 'error':
          console.error('Error:', data.message);
          eventSource.close();
          break;
      }
    };

    return () => {
      eventSource.close();
    };
  }, [filename]);

  return (
    <div>
      <div className="progress-bar">
        <div style={{ width: `${progress}%` }} />
      </div>

      <video ref={videoRef} controls style={{ width: '100%' }} />

      <div>
        Loaded chunks: {chunks.length}
        {!isComplete && ' (loading...)'}
      </div>
    </div>
  );
}
```

---

### Option C: Vanilla JavaScript (No Framework)

```html
<!DOCTYPE html>
<html>
<head>
  <title>Streaming Video Commentary</title>
  <style>
    .progress-bar {
      width: 100%;
      height: 30px;
      background: #ddd;
      margin: 20px 0;
    }
    .progress {
      height: 100%;
      background: #4CAF50;
      transition: width 0.3s;
    }
    video {
      width: 100%;
      max-width: 800px;
    }
  </style>
</head>
<body>
  <h1>Streaming Video Analysis</h1>

  <div id="status">Starting...</div>
  <div class="progress-bar">
    <div class="progress" id="progress" style="width: 0%"></div>
  </div>

  <video id="video" controls></video>

  <div id="chunk-info"></div>

  <script>
    const filename = 'your-video.mp4';
    const eventSource = new EventSource(`/api/analyze-stream/${filename}`);

    const chunks = [];
    let currentChunkIndex = 0;

    const video = document.getElementById('video');
    const statusDiv = document.getElementById('status');
    const progressBar = document.getElementById('progress');
    const chunkInfo = document.getElementById('chunk-info');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          statusDiv.textContent = data.message;
          progressBar.style.width = data.progress + '%';
          break;

        case 'chunk_ready':
          console.log('Chunk ready:', data.index, data.url);

          chunks.push({
            index: data.index,
            url: data.url,
            startTime: data.start_time,
            endTime: data.end_time
          });

          // Play first chunk immediately
          if (data.index === 0) {
            video.src = data.url;
            video.play();
          }

          progressBar.style.width = data.progress + '%';
          chunkInfo.textContent = `Loaded ${chunks.length} chunk(s)`;
          break;

        case 'complete':
          statusDiv.textContent = 'Processing complete!';
          progressBar.style.width = '100%';
          eventSource.close();
          break;

        case 'error':
          statusDiv.textContent = 'Error: ' + data.message;
          eventSource.close();
          break;
      }
    };

    // Handle video ended - play next chunk
    video.addEventListener('ended', () => {
      const nextIndex = currentChunkIndex + 1;

      if (nextIndex < chunks.length) {
        video.src = chunks[nextIndex].url;
        video.play();
        currentChunkIndex = nextIndex;
      } else {
        console.log('All chunks played');
      }
    });

    eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      statusDiv.textContent = 'Connection error';
      eventSource.close();
    };
  </script>
</body>
</html>
```

---

## Testing the API

### Using curl

```bash
# Test SSE endpoint
curl -N http://localhost:8000/api/analyze-stream/test-video.mp4
```

### Using JavaScript in Browser Console

```javascript
const eventSource = new EventSource('/api/analyze-stream/test-video.mp4');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};

eventSource.onerror = (error) => {
  console.error('Error:', error);
  eventSource.close();
};
```

---

## Performance Considerations

### Time to First Chunk

Expected timeline for a 133-second video:
- Video upload: ~10 seconds
- First interval analysis (30s): ~8 seconds
- Commentary generation: ~3 seconds
- TTS generation: ~3 seconds
- Chunk creation: ~2 seconds
- **Total: ~26 seconds to first playback**

This is **3x faster** than the batch system (77 seconds).

### Chunk Buffering Strategy

For smoother playback, consider buffering 2-3 chunks before starting:

```javascript
const MIN_BUFFER_CHUNKS = 2;

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'chunk_ready') {
    chunks.push(data);

    // Start playing only after buffering N chunks
    if (chunks.length >= MIN_BUFFER_CHUNKS && !hasStartedPlaying) {
      video.src = chunks[0].url;
      video.play();
      hasStartedPlaying = true;
    }
  }
};
```

---

## Error Handling

### Retry Logic

```javascript
function connectWithRetry(filename, maxRetries = 3) {
  let retryCount = 0;

  function connect() {
    const eventSource = new EventSource(`/api/analyze-stream/${filename}`);

    eventSource.onerror = (error) => {
      console.error('Connection error:', error);
      eventSource.close();

      if (retryCount < maxRetries) {
        retryCount++;
        console.log(`Retrying... (${retryCount}/${maxRetries})`);
        setTimeout(connect, 2000 * retryCount); // Exponential backoff
      } else {
        console.error('Max retries reached');
      }
    };

    // ... handle other events
  }

  connect();
}
```

### Missing Chunks

If a chunk fails to load:

```javascript
video.addEventListener('error', (e) => {
  console.error('Video playback error:', e);

  // Skip to next chunk
  const nextIndex = currentChunkIndex + 1;
  if (nextIndex < chunks.length) {
    video.src = chunks[nextIndex].url;
    video.play();
    currentChunkIndex = nextIndex;
  }
});
```

---

## Browser Compatibility

### EventSource Support
- Chrome: ✓ Full support
- Firefox: ✓ Full support
- Safari: ✓ Full support
- Edge: ✓ Full support
- IE11: ✗ No support (use polyfill)

### Polyfill for IE11

```html
<script src="https://cdn.jsdelivr.net/npm/event-source-polyfill@1.0.25/src/eventsource.min.js"></script>
```

---

## Next Steps

1. Implement one of the player options above
2. Test with sample video
3. Monitor performance metrics (time to first chunk)
4. Add UI for progress visualization
5. Implement error handling and retry logic
6. Consider adding quality selector (if implementing multiple quality streams)

---

## API Response Examples

### Full SSE Stream

```
data: {"type":"status","message":"Starting video analysis...","progress":0}

data: {"type":"status","message":"Uploading video to analysis service...","progress":10}

data: {"type":"status","message":"Video ready for analysis (133.0s)","progress":15}

data: {"type":"chunk_ready","index":0,"url":"/videos/streaming/session_20250116_143022/chunk_0.mp4","start_time":"00:00:23","end_time":"00:00:35","progress":25}

data: {"type":"chunk_ready","index":1,"url":"/videos/streaming/session_20250116_143022/chunk_1.mp4","start_time":"00:00:47","end_time":"00:00:58","progress":45}

data: {"type":"chunk_ready","index":2,"url":"/videos/streaming/session_20250116_143022/chunk_2.mp4","start_time":"00:01:15","end_time":"00:01:28","progress":65}

data: {"type":"status","message":"Finalizing video...","progress":95}

data: {"type":"complete","chunks":3,"final_video":"commentary_20250116_143022.mp4","progress":100}
```

---

**Last updated:** 2025-01-16
