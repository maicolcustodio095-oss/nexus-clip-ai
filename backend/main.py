
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from urllib.parse import urlparse, parse_qs, quote
from uuid import uuid4
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from threading import Lock
import subprocess
import os
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import imageio_ffmpeg

VERSION = "0.4.0"

app = FastAPI(
    title="NEXUS CLIP AI API",
    version=VERSION
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
    ".mp4", ".mov", ".webm",
    ".mp3", ".wav", ".m4a"
}

SESSIONS = {}
SESSION_LOCK = Lock()
MAX_SESSIONS = 100


class VideoRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    mode: str = "video"


class LiveRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)


def now():
    return datetime.now(timezone.utc).isoformat()


def request_json(url, headers=None):
    req = Request(
        url,
        headers=headers or {
            "User-Agent": "NEXUS-CLIP-AI/0.4"
        }
    )

    try:
        with urlopen(req, timeout=12) as response:
            return json.load(response)

    except HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(
                503,
                "Credenciales inválidas o sin permisos."
            )

        if exc.code == 429:
            raise HTTPException(
                503,
                "Límite de consultas alcanzado."
            )

        raise HTTPException(
            502,
            "La plataforma no pudo responder."
        )

    except (URLError, TimeoutError, ValueError):
        raise HTTPException(
            502,
            "No fue posible contactar la plataforma."
        )


def identify_platform(url):
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError()

    except ValueError:
        raise HTTPException(
            400,
            "Introduce un enlace HTTPS válido."
        )

    if host in (
        "youtu.be",
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com"
    ):
        return "youtube", parsed

    if host in (
        "twitch.tv",
        "www.twitch.tv",
        "m.twitch.tv"
    ):
        return "twitch", parsed

    raise HTTPException(
        400,
        "Solo se admiten YouTube y Twitch."
    )


def extract_target(platform, parsed):
    parts = [
        p for p in parsed.path.split("/") if p
    ]

    if platform == "twitch":
        if (
            len(parts) != 1
            or not parts[0].replace("_", "").isalnum()
        ):
            raise HTTPException(
                400,
                "Usa https://www.twitch.tv/canal"
            )

        return parts[0].lower()

    host = (parsed.hostname or "").lower()

    if host == "youtu.be":
        video_id = (
            parts[0] if len(parts) == 1 else ""
        )

    elif parts[:1] == ["watch"]:
        video_id = parse_qs(
            parsed.query
        ).get("v", [""])[0]

    elif (
        len(parts) == 2
        and parts[0] in (
            "live", "shorts", "embed"
        )
    ):
        video_id = parts[1]

    else:
        video_id = ""

    if (
        len(video_id) != 11
        or not all(
            c.isalnum() or c in "_-"
            for c in video_id
        )
    ):
        raise HTTPException(
            400,
            "Usa el enlace directo de YouTube."
        )

    return video_id


def twitch_token():
    client_id = os.getenv(
        "TWITCH_CLIENT_ID", ""
    ).strip()

    secret = os.getenv(
        "TWITCH_CLIENT_SECRET", ""
    ).strip()

    if not client_id or not secret:
        raise HTTPException(
            503,
            "Twitch no está configurado en Render."
        )

    url = (
        "https://id.twitch.tv/oauth2/token"
        "?client_id=" + quote(client_id)
        + "&client_secret=" + quote(secret)
        + "&grant_type=client_credentials"
    )

    try:
        req = Request(
            url,
            data=b"",
            method="POST"
        )

        with urlopen(req, timeout=12) as response:
            return (
                client_id,
                json.load(response)["access_token"]
            )

    except (
        HTTPError,
        URLError,
        TimeoutError,
        KeyError,
        ValueError
    ):
        raise HTTPException(
            503,
            "No se pudo autenticar con Twitch."
        )


def live_status(url):
    platform, parsed = identify_platform(url)

    target = extract_target(
        platform, parsed
    )

    if platform == "twitch":
        client_id, token = twitch_token()

        data = request_json(
            "https://api.twitch.tv/helix/streams"
            "?user_login=" + quote(target),
            {
                "Client-ID": client_id,
                "Authorization": "Bearer " + token
            }
        )

        streams = data.get("data", [])
        stream = streams[0] if streams else None

        return {
            "platform": "twitch",
            "target": target,
            "is_live": bool(stream),
            "title": (
                stream.get("title")
                if stream else None
            ),
            "viewer_count": (
                stream.get("viewer_count")
                if stream else None
            ),
            "checked_at": now()
        }

    key = os.getenv(
        "YOUTUBE_API_KEY", ""
    ).strip()

    if not key:
        raise HTTPException(
            503,
            "YouTube no está configurado en Render."
        )

    data = request_json(
        "https://www.googleapis.com/youtube/v3/videos"
        "?part=snippet,liveStreamingDetails"
        "&id=" + quote(target)
        + "&key=" + quote(key)
    )

    items = data.get("items", [])

    if not items:
        raise HTTPException(
            404,
            "No se encontró el video público."
        )

    item = items[0]

    details = item.get(
        "liveStreamingDetails", {}
    )

    broadcast = item.get(
        "snippet", {}
    ).get("liveBroadcastContent")

    is_live = (
        broadcast == "live"
        and bool(
            details.get("actualStartTime")
        )
        and not details.get("actualEndTime")
    )

    return {
        "platform": "youtube",
        "target": target,
        "is_live": is_live,
        "title": item.get(
            "snippet", {}
        ).get("title"),
        "viewer_count": None,
        "checked_at": now()
    }


def ffmpeg_path():
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()

        if os.path.isfile(path):
            return path

    except Exception:
        pass

    raise HTTPException(
        503,
        "FFmpeg no está disponible."
    )


@app.get("/")
def home():
    return {
        "project": "NEXUS CLIP AI",
        "engine": "NEXUS ENGINE",
        "version": VERSION,
        "status": "online",
        "automatic_clipping_enabled": False,
        "live_monitoring_enabled": False
    }


@app.get("/health")
def health():
    try:
        ffmpeg_path()
        available = True

    except HTTPException:
        available = False

    return {
        "status": "ok",
        "version": VERSION,
        "ffmpeg_available": available,
        "twitch_configured": bool(
            os.getenv("TWITCH_CLIENT_ID")
            and os.getenv("TWITCH_CLIENT_SECRET")
        ),
        "youtube_configured": bool(
            os.getenv("YOUTUBE_API_KEY")
        )
    }


@app.post("/api/analyze")
def analyze(request: VideoRequest):
    if request.mode not in (
        "video", "live"
    ):
        raise HTTPException(
            400,
            "Modo no válido."
        )

    platform, _ = identify_platform(
        request.url
    )

    return {
        "success": True,
        "job_id": str(uuid4()),
        "platform": platform,
        "mode": request.mode,
        "status": "not_started",
        "ai_processing": False,
        "message": (
            "Enlace validado. "
            "La IA aún no está disponible."
        )
    }


@app.post("/api/live/check")
def check_live(request: LiveRequest):
    return {
        "success": True,
        **live_status(request.url)
    }


@app.post("/api/live/sessions")
def create_session(request: LiveRequest):
    status = live_status(request.url)

    if not status["is_live"]:
        raise HTTPException(
            409,
            "La transmisión no está en vivo."
        )

    session = {
        "session_id": str(uuid4()),
        "url": request.url,
        "platform": status["platform"],
        "target": status["target"],
        "created_at": now(),
        "status": "registered",
        "monitoring_active": False,
        "clips_generated": 0,
        "last_check": status
    }

    with SESSION_LOCK:
        if len(SESSIONS) >= MAX_SESSIONS:
            raise HTTPException(
                503,
                "Límite de sesiones alcanzado."
            )

        SESSIONS[
            session["session_id"]
        ] = session

    return {
        "success": True,
        **session,
        "message": (
            "Sesión registrada. "
            "El monitoreo automático "
            "todavía no está activo."
        )
    }


@app.get("/api/live/sessions/{session_id}")
def get_session(session_id: str):
    with SESSION_LOCK:
        session = SESSIONS.get(
            session_id
        )

        if not session:
            raise HTTPException(
                404,
                "Sesión no encontrada o servidor reiniciado."
            )

        return dict(session)


@app.post("/api/process-upload")
def process_upload(
    file: UploadFile = File(...)
):
    extension = Path(
        file.filename or ""
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "Formato no admitido."
        )

    ffmpeg = ffmpeg_path()

    with TemporaryDirectory() as directory:
        source = os.path.join(
            directory,
            "source" + extension
        )

        output = os.path.join(
            directory,
            "audio.wav"
        )

        total = 0

        try:
            with open(
                source, "wb"
            ) as destination:

                while True:
                    chunk = file.file.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    total += len(chunk)

                    if total > MAX_FILE_SIZE:
                        raise HTTPException(
                            413,
                            "El archivo supera 15 MB."
                        )

                    destination.write(chunk)

            if not total:
                raise HTTPException(
                    400,
                    "Archivo vacío."
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
                    408,
                    "El procesamiento tardó demasiado."
                )

            except subprocess.CalledProcessError:
                raise HTTPException(
                    422,
                    "No se pudo extraer el audio."
                )

            if not os.path.isfile(output):
                raise HTTPException(
                    422,
                    "No se generó audio."
                )

            return {
                "success": True,
                "job_id": str(uuid4()),
                "status": "audio_extracted",
                "input_bytes": total,
                "audio_bytes": os.path.getsize(
                    output
                ),
                "audio_format": "wav",
                "sample_rate": 16000,
                "channels": 1,
                "max_audio_seconds": 120,
                "transcription": "not_started",
                "message": (
                    "Audio extraído. "
                    "Todavía no se conserva "
                    "ni se transcribe."
                )
            }

        finally:
            file.file.close()


@app.get("/api/capabilities")
def capabilities():
    return {
        "version": VERSION,
        "supported_platforms": [
            "youtube",
            "twitch"
        ],
        "available_features": [
            "url_validation",
            "platform_detection",
            "live_status_check_with_credentials",
            "temporary_live_session_registration",
            "audio_extraction_from_upload"
        ],
        "planned_features": [
            "persistent_sessions",
            "user_authentication",
            "continuous_live_monitoring",
            "chat_analysis",
            "automatic_transcription",
            "highlight_detection",
            "automatic_clipping",
            "face_tracking",
            "animated_subtitles",
            "viral_score",
            "social_publishing",
            "subscriptions"
        ]
            }
    
