
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib.parse import urlparse
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import shutil
import os

app = FastAPI(
    title="NEXUS CLIP AI API",
    description="NEXUS ENGINE - procesamiento multimedia",
    version="0.3.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://maicolcustodio095-oss.github.io"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"]
)

MAX_FILE_SIZE = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a"
}


class VideoRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    mode: str = "video"


@app.get("/")
def home():
    return {
        "project": "NEXUS CLIP AI",
        "engine": "NEXUS ENGINE",
        "version": "0.3.0",
        "status": "online",
        "transcription_enabled": False,
        "automatic_clipping_enabled": False
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "nexus-clip-ai-api",
        "version": "0.3.0",
        "ffmpeg_available": shutil.which("ffmpeg") is not None
    }


def identify_platform(url):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise HTTPException(400, "Enlace inválido.")

    if parsed.scheme != "https":
        raise HTTPException(400, "Utiliza HTTPS.")

    if parsed.username or parsed.password:
        raise HTTPException(400, "Credenciales no permitidas.")

    if host == "youtu.be" or (
        host == "youtube.com" or
        host.endswith(".youtube.com")
    ):
        return "youtube"

    if host == "twitch.tv" or host.endswith(".twitch.tv"):
        return "twitch"

    raise HTTPException(
        400, "Solo se admiten YouTube y Twitch."
    )


@app.post("/api/analyze")
def analyze(request: VideoRequest):
    if request.mode not in ("video", "live"):
        raise HTTPException(400, "Modo no válido.")

    platform = identify_platform(request.url)

    return {
        "success": True,
        "job_id": str(uuid4()),
        "platform": platform,
        "mode": request.mode,
        "status": "not_started",
        "ai_processing": False,
        "message": "Enlace validado. IA pendiente."
    }


@app.post("/api/process-upload")
def process_upload(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400, "Formato no admitido."
        )

    if not shutil.which("ffmpeg"):
        raise HTTPException(
            503, "FFmpeg no está instalado en el servidor."
        )

    job_id = str(uuid4())

    with TemporaryDirectory() as temp_dir:
        source = os.path.join(
            temp_dir, "source" + extension
        )
        output = os.path.join(
            temp_dir, "audio.wav"
        )

        total_size = 0

        try:
            with open(source, "wb") as destination:
                while True:
                    chunk = file.file.read(1024 * 1024)
                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            413,
                            "El archivo supera el límite de 15 MB."
                        )

                    destination.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    400, "El archivo está vacío."
                )

            command = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", source,
                "-map", "0:a:0",
                "-vn",
                "-t", "120",
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
                output
            ]

            try:
                subprocess.run(
                    command,
                    capture_output=True,
                    timeout=45,
                    check=True
                )
            except subprocess.TimeoutExpired:
                raise HTTPException(
                    408, "El procesamiento tardó demasiado."
                )
            except subprocess.CalledProcessError:
                raise HTTPException(
                    422,
                    "No se pudo extraer el audio."
                )

            if not os.path.isfile(output):
                raise HTTPException(
                    422, "No se generó audio."
                )

            audio_size = os.path.getsize(output)

            return {
                "success": True,
                "job_id": job_id,
                "status": "audio_extracted",
                "input_bytes": total_size,
                "audio_bytes": audio_size,
                "audio_format": "wav",
                "sample_rate": 16000,
                "channels": 1,
                "max_audio_seconds": 120,
                "transcription": "not_started",
                "message": (
                    "Audio extraído correctamente. "
                    "La transcripción todavía no está activa."
                )
            }

        finally:
            file.file.close()


@app.get("/api/capabilities")
def capabilities():
    return {
        "version": "0.3.0",
        "supported_platforms": ["youtube", "twitch"],
        "available_features": [
            "url_validation",
            "platform_detection",
            "audio_extraction_from_upload"
        ],
        "planned_features": [
            "automatic_transcription",
            "highlight_detection",
            "automatic_clipping",
            "vertical_video",
            "subtitles",
            "mp4_export"
        ]
    }
    
