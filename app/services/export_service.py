"""Fusion des séquences (ordre courant) et export vers un fichier final."""

from pathlib import Path

from app.models.project import Project
from app.services.ffmpeg_service import FFmpegService


class ExportError(RuntimeError):
    """Erreur utilisateur claire lors de la fusion/export."""


def merge_sequences(project: Project, ffmpeg_service: FFmpegService) -> str:
    """Concatène les séquences dans leur ordre courant vers temp/project_x/final.wav."""
    if not project.sequences:
        raise ExportError("Aucune séquence à fusionner. Créez au moins une séquence.")

    ordered = sorted(project.sequences, key=lambda seq: seq.order)
    out_path = str(Path(project.temp_dir) / "final.wav")
    paths = [seq.effective_audio_path for seq in ordered]

    if project.crossfade_duration > 0 and len(paths) > 1:
        ffmpeg_service.concat_with_crossfade(paths, out_path, project.crossfade_duration)
    else:
        ffmpeg_service.concat_audio(paths, out_path)

    return out_path


def export_project(project: Project, ffmpeg_service: FFmpegService, out_path: str, fmt: str, quality: str) -> None:
    """Fusionne puis exporte le résultat final vers out_path au format/qualité choisis."""
    final_wav = merge_sequences(project, ffmpeg_service)
    ffmpeg_service.export_audio(final_wav, out_path, fmt, quality)
