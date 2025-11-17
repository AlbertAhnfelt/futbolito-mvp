from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import json
from video_analysis.controller import list_videos, analyze_video
from video_analysis.context_manager import get_context_manager, MatchContext
from video_analysis.streaming_pipeline import streaming_pipeline

router = APIRouter()


class AnalyzeRequest(BaseModel):
    filename: str
    language: str = "en"  # ✅ changed: add language field with default "en"


@router.get("/videos/list")
async def get_videos_list():
    """List all available video files in the videos directory."""
    try:
        videos = list_videos()
        return JSONResponse(content=videos)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_video_endpoint(request: AnalyzeRequest):
    """Analyze a video file and extract football highlights."""
    try:
        if not request.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        # ✅ changed: pass language through to the controller
        highlights = await analyze_video(request.filename, request.language)
        return JSONResponse(content=highlights)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze-stream/{filename}")
async def analyze_video_stream(filename: str):
    """
    Stream video generation progress via Server-Sent Events (SSE).

    Returns chunks as they become available, enabling progressive playback.

    Event types:
    - status: Progress updates
    - chunk_ready: New video chunk available for playback
    - complete: All processing finished
    - error: Processing error occurred
    """
    try:
        if not filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        async def event_generator():
            try:
                async for event in streaming_pipeline(filename):
                    # Format as SSE event
                    yield f"data: {json.dumps(event)}\n\n"
            except Exception as e:
                # Send error event
                error_event = {
                    'type': 'error',
                    'message': str(e)
                }
                yield f"data: {json.dumps(error_event)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Connection": "keep-alive"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/videos/generated/{filename}")
async def get_generated_video(filename: str):
    """Serve a generated video file."""
    try:
        # Get the path to the generated video
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos' / 'generated-videos'
        video_path = videos_dir / filename

        if not video_path.exists():
            raise HTTPException(status_code=404, detail=f"Generated video {filename} not found")

        return FileResponse(
            path=str(video_path),
            media_type="video/mp4",
            filename=filename
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/videos/streaming/{session_id}/{chunk_filename}")
async def get_streaming_chunk(session_id: str, chunk_filename: str):
    """Serve a streaming video chunk."""
    try:
        # Get the path to the chunk
        videos_dir = Path(__file__).parent.parent.parent.parent / 'videos'
        chunk_path = videos_dir / 'streaming' / session_id / chunk_filename

        if not chunk_path.exists():
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_filename} not found")

        return FileResponse(
            path=str(chunk_path),
            media_type="video/mp4",
            filename=chunk_filename,
            headers={
                "Accept-Ranges": "bytes",  # Enable partial content support
                "Cache-Control": "public, max-age=31536000"  # Cache chunks for 1 year
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match-context")
async def save_match_context(context: MatchContext):
    """Save match context (team names, player info) for commentary generation."""
    try:
        context_manager = get_context_manager()
        context_manager.save_context(context)
        return JSONResponse(content={"message": "Match context saved successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/match-context")
async def get_match_context():
    """Get the current match context."""
    try:
        context_manager = get_context_manager()
        context = context_manager.load_context()

        if context is None:
            return JSONResponse(content=None)

        return JSONResponse(content=context.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/match-context")
async def clear_match_context():
    """Clear/reset the match context."""
    try:
        context_manager = get_context_manager()
        context_manager.clear_context()
        return JSONResponse(content={"message": "Match context cleared successfully"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
async def get_events():
    """Get the events.json file with detected events."""
    try:
        # Get the path to events.json in the output directory
        events_file = Path(__file__).parent.parent.parent.parent / 'output' / 'events.json'

        if not events_file.exists():
            return JSONResponse(content={"events": []})

        return FileResponse(
            path=str(events_file),
            media_type="application/json"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
