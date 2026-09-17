"""Une séquence audio découpée depuis la piste source."""

from dataclasses import dataclass, field

from app.models.audio_settings import AudioSettings


@dataclass
class Sequence:
    id: str
    name: str
    source_start: float
    source_end: float
    order: int
    audio_path: str = ""
    processed_audio_path: str = ""
    audio_settings: AudioSettings = field(default_factory=AudioSettings)

    @property
    def duration(self) -> float:
        return self.source_end - self.source_start

    @property
    def effective_audio_path(self) -> str:
        """Chemin à utiliser pour la lecture/fusion : traité si disponible, sinon brut."""
        return self.processed_audio_path or self.audio_path
