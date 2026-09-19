"""Fusion des séquences (ordre courant) et export vers un fichier final."""

import re
from pathlib import Path

from app.audio.filters import normalize_filter
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


def _normalized_copy(
    ffmpeg_service: FFmpegService, source_wav: str, out_wav: Path, target_lufs: float
) -> str:
    """Écrit une version au volume normalisé (loudness EBU R128) de source_wav ; l'original reste intact."""
    ffmpeg_service.apply_filters(source_wav, str(out_wav), normalize_filter("loudness", target_lufs))
    return str(out_wav)


def export_project(
    project: Project,
    ffmpeg_service: FFmpegService,
    out_path: str,
    fmt: str,
    quality: str,
    normalize_lufs: float | None = None,
) -> None:
    """Fusionne puis exporte le résultat final vers out_path au format/qualité choisis.

    Si `normalize_lufs` est fourni, le volume du résultat fusionné est normalisé à ce niveau avant l'export.
    """
    final_wav = merge_sequences(project, ffmpeg_service)
    if normalize_lufs is not None:
        final_wav = _normalized_copy(ffmpeg_service, final_wav, Path(project.temp_dir) / "final_normalized.wav", normalize_lufs)
    ffmpeg_service.export_audio(final_wav, out_path, fmt, quality)


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\|?*\x00-\x1f]', "_", name).strip(" .") or "sequence"


def export_sequences_separately(
    project: Project,
    ffmpeg_service: FFmpegService,
    out_dir: str,
    fmt: str,
    quality: str,
    normalize_lufs: float | None = None,
) -> list[str]:
    """Exporte chaque séquence (version traitée si disponible) dans son propre fichier, dans out_dir."""
    if not project.sequences:
        raise ExportError("Aucune séquence à exporter. Créez au moins une séquence.")

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for index, seq in enumerate(sorted(project.sequences, key=lambda s: s.order), start=1):
        target = directory / f"{index:02d}_{_safe_filename(seq.name)}.{fmt.lower()}"
        source = seq.effective_audio_path
        if normalize_lufs is not None:
            source = _normalized_copy(
                ffmpeg_service, source, Path(project.temp_dir) / f"export_norm_{seq.id}.wav", normalize_lufs
            )
        ffmpeg_service.export_audio(source, str(target), fmt, quality)
        written.append(str(target))
    return written
