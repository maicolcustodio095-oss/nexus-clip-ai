
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib.parse import urlparse
from uuid import uuid4
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import os
import imageio_ffmpeg


# ==========================================
# NEXUS CLIP AI - ENGINE 0.3
# ==========================================

app = FastAPI(
    title="NEXUS CLIP AI API",
    description="Motor de procesamiento multimedia",
    version="0.3.0"
)


# ==========================================
# CONEXION CON NUESTRA PAGINA
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://maicolcustodio095-oss.github.io"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"]
)


# ==========================================
# CONFIGURACION
# ==========================================

MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".mp3",
    ".wav",
    ".m4a"
}


class VideoRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    mode: str = "video"


# ==========================================
# MOTOR FFMPEG
# ==========================================

def get_ffmpeg():
    try:
        executable = imageio_ffmpeg.get_ffmpeg_exe()

        if not os.path.isfile(executable):
            raise RuntimeError("FFmpeg no encontrado")

        return executable

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="El motor FFmpeg no está disponible."
        )


# ==========================================
# ESTADO DEL SERVIDOR
# ==========================================

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
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_available = os.path.isfile(ffmpeg)
    except Exception:
        ffmpeg_available = False

    return {
        "status": "ok",
        "service": "nexus-clip-ai-api",
        "version": "0.3.0",
        "ffmpeg_available": ffmpeg_available
    }


# ==========================================
# IDENTIFICAR YOUTUBE Y TWITCH
# ==========================================

def identify_platform(url):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Enlace inválido."
        )

    if parsed.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="Utiliza un enlace HTTPS."
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail="No se permiten credenciales."
        )

    if host == "youtu.be" or (
        host == "youtube.com"
        or host.endswith(".youtube.com")
    ):
        return "youtube"

    if host == "twitch.tv" or host.endswith(".twitch.tv"):
        return "twitch"

    raise HTTPException(
        status_code=400,
        detail="Solo admitimos YouTube y Twitch."
    )


# ==========================================
# VERIFICAR ENLACES
# ==========================================

@app.post("/api/analyze")
def analyze(request: VideoRequest):

    if request.mode not in ["video", "live"]:
        raise HTTPException(
            status_code=400,
            detail="Modo no válido."
        )

    platform = identify_platform(request.url)

    return {
        "success": True,
        "job_id": str(uuid4()),
        "platform": platform,
        "mode": request.mode,
        "status": "not_started",
        "ai_processing": False,
        "message": (
            "Enlace recibido correctamente. "
            "El análisis con IA aún no está disponible."
        )
    }


# ==========================================
# EXTRAER AUDIO DE ARCHIVOS
# ==========================================

@app.post("/api/process-upload")
def process_upload(file: UploadFile = File(...)):

    extension = Path(
        file.filename or ""
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato de archivo no admitido."
        )

    ffmpeg = get_ffmpeg()
    job_id = str(uuid4())

    with TemporaryDirectory() as temp_dir:

        source = os.path.join(
            temp_dir,
            "source" + extension
        )

        output = os.path.join(
            temp_dir,
            "audio.wav"
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
                            status_code=413,
                            detail=(
                                "El archivo supera "
                                "el límite de 15 MB."
                            )
                        )

                    destination.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo está vacío."
                )

            command = [
                ffmpeg,
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
                    status_code=408,
                    detail=(
                        "El procesamiento tardó demasiado."
                    )
                )

            except subprocess.CalledProcessError:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "No se pudo extraer el audio. "
                        "Comprueba que el archivo sea válido."
                    )
                )

            if not os.path.isfile(output):
                raise HTTPException(
                    status_code=422,
                    detail="No se generó el audio."
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
                    "La transcripción con IA "
                    "todavía no está disponible."
                )
            }

        finally:
            file.file.close()


# ==========================================
# CAPACIDADES DEL SISTEMA
# ==========================================

@app.get("/api/capabilities")
def capabilities():

    return {
        "project": "NEXUS CLIP AI",
        "version": "0.3.0",
        "supported_platforms": [
            "youtube",
            "twitch"
        ],
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
            "automatic_subtitles",
            "mp4_export"
        ]
                        }
    
