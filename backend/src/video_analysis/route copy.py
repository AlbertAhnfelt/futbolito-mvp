from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import glob
from pydantic import BaseModel
from pathlib import Path
import json
from video_analysis.controller import list_videos, analyze_video
from video_analysis.context_manager import get_context_manager, MatchContext
# from video_analysis.streaming_pipeline import streaming_pipeline
from video_analysis.test_streaming import WebcamGeminiProcessor
# from video_analysis.test_streaming import StreamProcessor

router = APIRouter()


class AnalyzeRequest(BaseModel):
    filename: str
    language: str = "en"  # ✅ changed: add language field with default "en"


# Configuration CORS pour que le frontend React puisse accéder aux vidéos
# router.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"], # À restreindre en prod
#     allow_methods=["*"],
#     allow_headers=["*"],
# )



# 1. Servir les fichiers vidéos MP4 de manière statique
# router.mount("/videos", StaticFiles(directory=BASE_VIDEO_DIR), name="videos")


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
    



@router.get("/outputs/{folder_name}/stream.m3u8")
async def get_playlist(folder_name: str):
    """
    Génère dynamiquement la playlist HLS en listant les fichiers MP4 présents.
    """
    folder_path = folder_name
    
    if not os.path.exists(folder_path):
        # Si le dossier n'existe pas encore (le process n'a pas commencé)
        raise HTTPException(status_code=404, detail="Stream not found or not started")

    # Récupérer les fichiers mp4 et les trier (par nom ou date de création)
    # Assumons que les fichiers sont nommés par ordre alphabétique ou numérotés
    files = sorted(glob.glob(os.path.join(folder_path, "*.mp4")))
    
    if not files:
        # Le dossier existe mais pas encore de vidéo (phase d'attente initiale)
        raise HTTPException(status_code=404, detail="No segments available yet")

    # Construction du contenu du fichier m3u8
    # #EXT-X-PLAYLIST-TYPE:EVENT signifie que la playlist s'allonge avec le temps
    content = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-TARGETDURATION:21",  # Un peu plus que vos 20s pour la marge
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:EVENT" 
    ]

    for file_path in files:
        filename = os.path.basename(file_path)
        # On suppose que chaque chunk fait environ 20s
        content.append(f"#EXTINF:20.0,")
        # L'URL vers le fichier statique
        content.append(f"http://localhost:8000/videos/{folder_name}/{filename}")

    # Si le stream est fini, on ajouterait #EXT-X-ENDLIST, mais ici on suppose que c'est en cours
    
    return Response(content="\n".join(content), media_type="application/vnd.apple.mpegurl")

@router.get("/analyze-stream/{filename}")
async def analyze_stream(filename: str):
    # Chemin vers la vidéo source
    video_path = f"../../videos/{filename}" 
    
    processor = WebcamGeminiProcessor(video_path)
    
    # On retourne une StreamingResponse qui va consommer le générateur
    return StreamingResponse(
        processor.stream_generator(), 
        media_type="text/event-stream"
    )

# @router.get("/outputs/{folder_name}/{filename}")
# async def get_output_file(folder_name: str, filename: str):

#     file_path = f"outputs/{folder_name}/{filename}"

#     if not file_path.exists():
#         raise HTTPException(status_code=404, detail="File not found")
    
#     # Détection simple du type MIME
#     media_type = "video/mp4"
#     if filename.endswith(".m3u8"):
#         media_type = "application/vnd.apple.mpegurl" # Type MIME pour HLS

#     return FileResponse(path=file_path, media_type=media_type)

# @router.get("/analyze-stream/{filename}")
# async def analyze_video_stream(filename: str):
#     """
#     Stream video generation progress via Server-Sent Events (SSE).

#     Returns chunks as they become available, enabling progressive playback.

#     Event types:
#     - status: Progress updates
#     - chunk_ready: New video chunk available for playback
#     - complete: All processing finished
#     - error: Processing error occurred
#     """
#     try:
#         if not filename:
#             raise HTTPException(status_code=400, detail="No filename provided")

#         async def event_generator():
#             try:
#                 async for event in streaming_pipeline(filename):
#                     # Format as SSE event
#                     yield f"data: {json.dumps(event)}\n\n"
#             except Exception as e:
#                 # Send error event
#                 error_event = {
#                     'type': 'error',
#                     'message': str(e)
#                 }
#                 yield f"data: {json.dumps(error_event)}\n\n"

#         return StreamingResponse(
#             event_generator(),
#             media_type="text/event-stream",
#             headers={
#                 "Cache-Control": "no-cache",
#                 "X-Accel-Buffering": "no",  # Disable nginx buffering
#                 "Connection": "keep-alive"
#             }
#         )

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


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
