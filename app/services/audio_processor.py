"""Application des paramètres de traitement audio (AudioSettings) à une séquence."""

from pathlib import Path
from uuid import uuid4

from app.audio.filters import build_filter_chain
from app.audio.silence_detection import compute_keep_ranges
from app.models.project import Project
from app.models.sequence import Sequence
from app.services.ffmpeg_service import FFmpegService


def remove_silences(project: Project, sequence: Sequence, ffmpeg_service: FFmpegService) -> tuple[str, float]:
    """Détecte et retire les silences de sequence.audio_path. Retourne (chemin, durée résultante)."""
    settings = sequence.audio_settings
    token = uuid4().hex[:6]
    silences = ffmpeg_service.detect_silences(
        sequence.audio_path, settings.silence_threshold_db, settings.silence_min_duration
    )
    keep_ranges = compute_keep_ranges(silences, sequence.duration, settings.silence_keep_padding)

    if not keep_ranges:
        return sequence.audio_path, sequence.duration

    segment_paths = []
    for index, (start, end) in enumerate(keep_ranges):
        segment_path = str(Path(project.temp_dir) / f"desilenced_{sequence.id}_{token}_{index}.wav")
        ffmpeg_service.cut_audio(sequence.audio_path, segment_path, start, end)
        segment_paths.append(segment_path)

    out_path = str(Path(project.temp_dir) / f"desilenced_{sequence.id}_{token}.wav")
    if len(segment_paths) == 1:
        Path(segment_paths[0]).replace(out_path)
    else:
        ffmpeg_service.concat_audio(segment_paths, out_path)
        for segment_path in segment_paths:
            Path(segment_path).unlink(missing_ok=True)

    total_duration = sum(end - start for start, end in keep_ranges)
    return out_path, total_duration


def process_sequence(project: Project, sequence: Sequence, ffmpeg_service: FFmpegService) -> str | None:
    """Applique sequence.audio_settings sur le fichier brut de la séquence.

    Écrit un fichier temp/project_x/processed_<id>_<jeton>.wav distinct à chaque appel (non destructif :
    audio_path original conservé, et les versions précédentes restent disponibles pour l'annulation). Retourne le chemin traité, ou None si aucun
    traitement n'est activé (auquel cas processed_audio_path est réinitialisé).
    """
    source_path = sequence.audio_path
    effective_duration = sequence.duration

    if sequence.audio_settings.silence_removal:
        source_path, effective_duration = remove_silences(project, sequence, ffmpeg_service)

    filter_chain = build_filter_chain(sequence.audio_settings, effective_duration)

    if filter_chain is None:
        if source_path != sequence.audio_path:
            sequence.processed_audio_path = source_path
            return source_path
        sequence.processed_audio_path = ""
        return None

    out_path = str(Path(project.temp_dir) / f"processed_{sequence.id}_{uuid4().hex[:6]}.wav")
    ffmpeg_service.apply_filters(source_path, out_path, filter_chain)
    sequence.processed_audio_path = out_path
    return out_path


def reset_processing(sequence: Sequence) -> None:
    """Réinitialise les paramètres de traitement et abandonne le fichier traité."""
    from app.models.audio_settings import AudioSettings

    sequence.audio_settings = AudioSettings()
    sequence.processed_audio_path = ""
