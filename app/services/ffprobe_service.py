"""Analyse des fichiers vidéo via FFprobe."""

import json
import subprocess
from pathlib import Path

from app.config.constants import SUPPORTED_VIDEO_FORMATS
from app.models.media import MediaInfo


class ProbeError(RuntimeError):
    """Erreur utilisateur claire lors de l'analyse d'un fichier vidéo."""


class FFprobeService:
    def __init__(self, ffprobe_path: str) -> None:
        self._ffprobe_path = ffprobe_path

    def probe(self, video_path: str) -> MediaInfo:
        path = Path(video_path)

        if not path.exists():
            raise ProbeError("Impossible d'ouvrir le fichier vidéo : le fichier n'existe pas.")

        if path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
            raise ProbeError(f"Le format '{path.suffix}' n'est pas supporté.")

        try:
            result = subprocess.run(
                [
                    self._ffprobe_path,
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProbeError("L'analyse du fichier vidéo a expiré.") from exc

        if result.returncode != 0:
            raise ProbeError("Le fichier vidéo semble corrompu ou illisible.")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProbeError("Impossible d'analyser les informations de la vidéo.") from exc

        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if audio_stream is None:
            raise ProbeError("Cette vidéo ne contient pas de piste audio.")

        fmt = data.get("format", {})
        duration = _parse_float(fmt.get("duration"))
        if duration is None:
            duration = _parse_float(audio_stream.get("duration")) or _parse_float(
                (video_stream or {}).get("duration")
            ) or 0.0

        resolution = None
        if video_stream and video_stream.get("width") and video_stream.get("height"):
            resolution = (int(video_stream["width"]), int(video_stream["height"]))

        return MediaInfo(
            path=str(path),
            duration=duration,
            container_format=fmt.get("format_name", ""),
            video_codec=video_stream.get("codec_name") if video_stream else None,
            audio_codec=audio_stream.get("codec_name", ""),
            sample_rate=int(audio_stream.get("sample_rate", 0)),
            channels=int(audio_stream.get("channels", 0)),
            resolution=resolution,
            bitrate=int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
            size_bytes=path.stat().st_size,
        )


def _parse_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
