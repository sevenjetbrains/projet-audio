"""Projet AudioCut Studio : vidéo source + liste de séquences ordonnées."""

from dataclasses import dataclass, field

from app.models.media import MediaInfo
from app.models.sequence import Sequence


@dataclass
class Project:
    name: str
    source_video: MediaInfo | None = None
    sequences: list[Sequence] = field(default_factory=list)
