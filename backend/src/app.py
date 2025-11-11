from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from video_analysis.route import router as video_router
from football_api.route import router as football_router

app = FastAPI(
    title="Futbolito MVP API",
    description="API for analyzing football match videos and extracting highlights",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video_router, prefix="/api")
app.include_router(football_router)


@app.get("/")
async def root():
    return {
        "message": "Futbolito MVP API",
        "docs": "/docs",
        "health": "ok"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

