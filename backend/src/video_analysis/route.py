from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from pathlib import Path
from video_analysis.controller import list_videos, analyze_video
from video_analysis.context_manager import get_context_manager, MatchContext

router = APIRouter()


class AnalyzeRequest(BaseModel):
    filename: str


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

        highlights = await analyze_video(request.filename)
        return JSONResponse(content=highlights)

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
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

