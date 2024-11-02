from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yt_dlp
import os
from pathlib import Path
import uuid
import json
from typing import Optional
import shutil

app = FastAPI(title="TikTok Video Downloader")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define base directory as current working directory
BASE_DIR = Path.cwd()
STATIC_DIR = BASE_DIR / "static"
DOWNLOADS_DIR = STATIC_DIR / "downloads"

# Create directories with error handling
def setup_directories():
    try:
        STATIC_DIR.mkdir(exist_ok=True)
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        
        # Ensure directories have proper permissions
        STATIC_DIR.chmod(0o755)
        DOWNLOADS_DIR.chmod(0o755)
        
        print(f"Directories setup complete. Downloads directory: {DOWNLOADS_DIR}")
        return True
    except Exception as e:
        print(f"Error setting up directories: {e}")
        return False

# Setup directories
if not setup_directories():
    raise Exception("Failed to setup required directories")

# Serve static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class DownloadRequest(BaseModel):
    url: str
    save_metadata: bool = True

def clean_old_files():
    """Clean up old downloaded files"""
    try:
        for file in DOWNLOADS_DIR.glob("*"):
            if file.is_file() and (file.suffix in ['.mp4', '.json']):
                file.unlink()
    except Exception as e:
        print(f"Error cleaning old files: {e}")

@app.post("/download")
async def download_video(request: DownloadRequest):
    # Clean old files before new download
    clean_old_files()
    
    try:
        video_id = str(uuid.uuid4())
        output_path = DOWNLOADS_DIR / f"{video_id}.mp4"
        
        print(f"Starting download to: {output_path}")
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': str(output_path),
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
            'extract_flat': False,
            'force_generic_extractor': False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download video and extract metadata
                info = ydl.extract_info(request.url, download=True)
                
                # Verify file exists
                if not output_path.exists():
                    raise HTTPException(
                        status_code=500,
                        detail="Video download failed - file not created"
                    )
                
                print(f"Download complete. File size: {output_path.stat().st_size} bytes")
                
                # Save metadata if requested
                if request.save_metadata and info:
                    metadata_file = DOWNLOADS_DIR / f"{video_id}_metadata.json"
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'title': info.get('title', ''),
                            'description': info.get('description', ''),
                            'uploader': info.get('uploader', ''),
                            'duration': info.get('duration', ''),
                            'view_count': info.get('view_count', ''),
                            'like_count': info.get('like_count', ''),
                            'comment_count': info.get('comment_count', ''),
                            'upload_date': info.get('upload_date', '')
                        }, f, ensure_ascii=False, indent=2)

                # Create response with absolute URL
                download_url = f"/static/downloads/{output_path.name}"
                print(f"Generated download URL: {download_url}")
                
                return JSONResponse({
                    "success": True,
                    "download_url": download_url,
                    "file_exists": output_path.exists(),
                    "file_size": output_path.stat().st_size,
                    "metadata": info if request.save_metadata else None
                })

        except Exception as e:
            print(f"Download error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Download failed: {str(e)}"
            )

    except Exception as e:
        print(f"Server error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Server error: {str(e)}"
        )

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/status")
async def api_root():
    return {
        "status": "ok",
        "message": "TikTok Video Downloader API is running",
        "downloads_dir": str(DOWNLOADS_DIR),
        "downloads_dir_exists": DOWNLOADS_DIR.exists(),
        "downloads_dir_writable": os.access(DOWNLOADS_DIR, os.W_OK)
    }

# Direct file download endpoint
@app.get("/download/{filename}")
async def get_file(filename: str):
    file_path = DOWNLOADS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=filename)

# Add an error handler for 404 errors
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": f"Path {request.url.path} not found"}
    )