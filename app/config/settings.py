"""Résolution des chemins runtime et détection des binaires FFmpeg/FFprobe."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config.constants import LOGS_DIR_NAME, TEMP_DIR_NAME

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMP_DIR = PROJECT_ROOT / TEMP_DIR_NAME
LOGS_DIR = PROJECT_ROOT / LOGS_DIR_NAME


class FFmpegNotFoundError(RuntimeError):
    """Levée quand ffmpeg ou ffprobe est introuvable sur le système."""


@dataclass
class FFmpegBinaries:
    ffmpeg_path: str
    ffprobe_path: str


def find_ffmpeg_binaries() -> FFmpegBinaries:
    """Localise ffmpeg et ffprobe sur le PATH.

    Lève FFmpegNotFoundError avec un message clair si l'un des deux est absent,
    plutôt que de laisser un FileNotFoundError brut remonter jusqu'à l'UI.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    missing = [name for name, path in (("ffmpeg", ffmpeg_path), ("ffprobe", ffprobe_path)) if path is None]
    if missing:
        raise FFmpegNotFoundError(
            "FFmpeg n'est pas installé ou n'est pas accessible.\n\n"
            "Veuillez installer FFmpeg puis redémarrer l'application.\n"
            f"(binaire(s) introuvable(s) sur le PATH : {', '.join(missing)})"
        )

    return FFmpegBinaries(ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)


def ensure_runtime_dirs() -> None:
    """Crée les dossiers temp/ et logs/ s'ils n'existent pas encore."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
