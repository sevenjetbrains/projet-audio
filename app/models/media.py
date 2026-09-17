"""Métadonnées d'un fichier vidéo/audio source, obtenues via FFprobe."""

from dataclasses import dataclass


@dataclass
class MediaInfo:
    path: str
    duration: float
    container_format: str
    video_codec: str | None
    audio_codec: str
    sample_rate: int
    channels: int
    resolution: tuple[int, int] | None
    bitrate: int | None
    size_bytes: int
