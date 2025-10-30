from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from pathlib import Path
from video_analysis.controller import list_videos, analyze_video

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

