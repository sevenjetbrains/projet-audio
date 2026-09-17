"""Paramètres de traitement audio non destructifs d'une séquence."""

from dataclasses import dataclass

NOISE_REDUCTION_LEVELS = ("faible", "moyenne", "forte")
NORMALIZE_MODES = ("peak", "loudness")


@dataclass
class AudioSettings:
    gain: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0

    noise_reduction: bool = False
    noise_reduction_level: str = "moyenne"

    de_hum: bool = False
    de_hum_freq: int = 50

    de_click: bool = False

    eq_bass_db: float = 0.0
    eq_mid_db: float = 0.0
    eq_treble_db: float = 0.0

    compression: bool = False

    normalize: bool = False
    normalize_mode: str = "peak"
    normalize_target_lufs: float = -16.0

    silence_removal: bool = False
    silence_threshold_db: float = -35.0
    silence_min_duration: float = 0.5
    silence_keep_padding: float = 0.1
