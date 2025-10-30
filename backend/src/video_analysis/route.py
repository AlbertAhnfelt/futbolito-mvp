from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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

