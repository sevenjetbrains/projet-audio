"""Fusion des séquences (ordre courant) et export vers un fichier final."""

import re
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


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\|?*\x00-\x1f]', "_", name).strip(" .") or "sequence"


def export_sequences_separately(
    project: Project, ffmpeg_service: FFmpegService, out_dir: str, fmt: str, quality: str
) -> list[str]:
    """Exporte chaque séquence (version traitée si disponible) dans son propre fichier, dans out_dir."""
    if not project.sequences:
        raise ExportError("Aucune séquence à exporter. Créez au moins une séquence.")

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for index, seq in enumerate(sorted(project.sequences, key=lambda s: s.order), start=1):
        target = directory / f"{index:02d}_{_safe_filename(seq.name)}.{fmt.lower()}"
        ffmpeg_service.export_audio(seq.effective_audio_path, str(target), fmt, quality)
        written.append(str(target))
    return written
