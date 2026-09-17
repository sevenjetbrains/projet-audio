"""Paramètres de traitement audio d'une séquence (remplis à partir de la Phase 2)."""

from dataclasses import dataclass


@dataclass
class AudioSettings:
    gain: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
