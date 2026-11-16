

from fastapi import FastAPI
from pydantic import BaseModel
from urllib.parse import urlparse
from uuid import uuid4

app = FastAPI(
    title="NEXUS CLIP AI API",
    version="0.1.0"
)

class VideoRequest(BaseModel):
    url: str
    mode: str = "video"

@app.get("/")
def home():
    return {
        "project": "NEXUS CLIP AI",
        "status": "online",
        "engine": "development"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/analyze")
def analyze(request: VideoRequest):
    if request.mode not in ("video", "live"):
        return {
            "success": False,
            "error": "Modo no válido"
        }

    try:
        parsed = urlparse(request.url.strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        host = ""
        parsed = None

    if not parsed or parsed.scheme != "https":
        return {
            "success": False,
            "error": "Se requiere un enlace HTTPS"
        }

    if host == "youtu.be" or (
        host == "youtube.com"
        or host.endswith(".youtube.com")
    ):
        platform = "youtube"

    elif host == "twitch.tv" or host.endswith(".twitch.tv"):
        platform = "twitch"

    else:
        return {
            "success": False,
            "error": "Plataforma no admitida"
        }

    return {
        "success": True,
        "job_id": str(uuid4()),
        "platform": platform,
        "mode": request.mode,
        "status": "not_started",
        "message": (
            "Enlace reconocido. "
            "El procesamiento con IA aún no está implementado."
        )
    }
