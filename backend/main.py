
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib.parse import urlparse
from uuid import uuid4
from datetime import datetime, timezone


# ========================================
# NEXUS CLIP AI - ENGINE 0.2
# ========================================

app = FastAPI(
    title="NEXUS CLIP AI API",
    description="Backend oficial de NEXUS CLIP AI",
    version="0.2.0"
)


# ========================================
# CONEXION CON NUESTRA PAGINA WEB
# ========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://maicolcustodio095-oss.github.io"
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ========================================
# MODELO DE SOLICITUD
# ========================================

class VideoRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    mode: str = "video"


# ========================================
# ESTADO DEL SERVIDOR
# ========================================

@app.get("/")
def home():
    return {
        "project": "NEXUS CLIP AI",
        "version": "0.2.0",
        "engine": "NEXUS ENGINE",
        "status": "online",
        "ai_processing": False
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "nexus-clip-ai-api",
        "version": "0.2.0"
    }


# ========================================
# VALIDACION DE PLATAFORMAS
# ========================================

def identify_platform(url: str):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="El enlace no es válido."
        )

    if parsed.scheme != "https":
        raise HTTPException(
            status_code=400,
            detail="Utiliza un enlace HTTPS."
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail="El enlace no debe contener credenciales."
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
        detail="Solo admitimos enlaces de YouTube y Twitch."
    )


# ========================================
# ANALISIS DE ENLACES
# ========================================

@app.post("/api/analyze")
def analyze(request: VideoRequest):

    if request.mode not in ["video", "live"]:
        raise HTTPException(
            status_code=400,
            detail="Modo no válido. Usa video o live."
        )

    platform = identify_platform(request.url)

    job_id = str(uuid4())

    return {
        "success": True,
        "job_id": job_id,
        "platform": platform,
        "mode": request.mode,
        "status": "not_started",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "ai_processing": False,
        "message": (
            "Enlace recibido correctamente. "
            "El análisis con IA todavía no está disponible."
        )
    }


# ========================================
# INFORMACION DE CAPACIDADES
# ========================================

@app.get("/api/capabilities")
def capabilities():
    return {
        "project": "NEXUS CLIP AI",
        "supported_platforms": [
            "youtube",
            "twitch"
        ],
        "available_features": [
            "url_validation",
            "platform_detection",
            "request_identification"
        ],
        "planned_features": [
            "video_transcription",
            "highlight_detection",
            "automatic_clipping",
            "vertical_video",
            "automatic_subtitles",
            "mp4_export"
        ]
    }
    
