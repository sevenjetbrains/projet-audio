"""Une séquence audio découpée depuis la piste source."""

from dataclasses import dataclass


@dataclass
class Sequence:
    id: str
    name: str
    source_start: float
    source_end: float
    order: int
    audio_path: str = ""

    @property
    def duration(self) -> float:
        return self.source_end - self.source_start
