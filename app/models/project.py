"""Projet AudioCut Studio : vidéo source + liste de séquences ordonnées."""

from dataclasses import dataclass, field

from app.models.marker import Marker
from app.models.media import MediaInfo
from app.models.sequence import Sequence


@dataclass
class Project:
    name: str
    source_video: MediaInfo | None = None
    sequences: list[Sequence] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    temp_dir: str = ""
    original_audio_path: str = ""
    crossfade_duration: float = 0.0
