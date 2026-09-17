"""Application des paramètres de traitement audio (AudioSettings) à une séquence."""

from pathlib import Path

from app.audio.filters import build_filter_chain
from app.models.project import Project
from app.models.sequence import Sequence
from app.services.ffmpeg_service import FFmpegService


def process_sequence(project: Project, sequence: Sequence, ffmpeg_service: FFmpegService) -> str | None:
    """Applique sequence.audio_settings sur le fichier brut de la séquence.

    Écrit un fichier temp/project_x/processed_<id>.wav distinct (non destructif :
    audio_path original conservé). Retourne le chemin traité, ou None si aucun
    traitement n'est activé (auquel cas processed_audio_path est réinitialisé).
    """
    filter_chain = build_filter_chain(sequence.audio_settings, sequence.duration)

    if filter_chain is None:
        sequence.processed_audio_path = ""
        return None

    out_path = str(Path(project.temp_dir) / f"processed_{sequence.id}.wav")
    ffmpeg_service.apply_filters(sequence.audio_path, out_path, filter_chain)
    sequence.processed_audio_path = out_path
    return out_path


def reset_processing(sequence: Sequence) -> None:
    """Réinitialise les paramètres de traitement et abandonne le fichier traité."""
    from app.models.audio_settings import AudioSettings

    sequence.audio_settings = AudioSettings()
    sequence.processed_audio_path = ""
