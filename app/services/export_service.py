"""Fusion des séquences (ordre courant) et export vers un fichier final."""

import re
from collections.abc import Callable
from pathlib import Path

from app.audio.filters import normalize_filter
from app.models.project import Project
from app.services.ffmpeg_service import FFmpegCancelled, FFmpegService
from app.utils.progress import ProgressCallback, sub_progress


class ExportError(RuntimeError):
    """Erreur utilisateur claire lors de la fusion/export."""


# Rapporte l'étape en cours pour que l'interface puisse l'écrire (« séquence 5 sur 8 « … » »).
StageCallback = Callable[[str], None]


def _announce(on_stage: StageCallback | None, message: str) -> None:
    if on_stage is not None:
        on_stage(message)


def _stop_if_cancelled(should_cancel: Callable[[], bool] | None) -> None:
    if should_cancel is not None and should_cancel():
        raise FFmpegCancelled("Export annulé.")


def merge_sequences(project: Project, ffmpeg_service: FFmpegService, on_progress: ProgressCallback | None = None) -> str:
    """Concatène les séquences dans leur ordre courant vers temp/project_x/final.wav."""
    if not project.sequences:
        raise ExportError("Aucune séquence à fusionner. Créez au moins une séquence.")

    ordered = sorted(project.sequences, key=lambda seq: seq.order)
    out_path = str(Path(project.temp_dir) / "final.wav")
    paths = [seq.effective_audio_path for seq in ordered]

    if project.crossfade_duration > 0 and len(paths) > 1:
        ffmpeg_service.concat_with_crossfade(paths, out_path, project.crossfade_duration, on_progress)
    else:
        ffmpeg_service.concat_audio(paths, out_path, on_progress)

    return out_path


def _normalized_copy(
    ffmpeg_service: FFmpegService,
    source_wav: str,
    out_wav: Path,
    target_lufs: float,
    on_progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    """Écrit une version au volume normalisé (loudness EBU R128) de source_wav ; l'original reste intact."""
    ffmpeg_service.apply_filters(
        source_wav, str(out_wav), normalize_filter("loudness", target_lufs), on_progress, should_cancel
    )
    return str(out_wav)


def export_project(
    project: Project,
    ffmpeg_service: FFmpegService,
    out_path: str,
    fmt: str,
    quality: str,
    normalize_lufs: float | None = None,
    on_progress: ProgressCallback | None = None,
    sample_rate: int | None = None,
    on_stage: StageCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Fusionne puis exporte le résultat final vers out_path au format/qualité choisis.

    Si `normalize_lufs` est fourni, le volume du résultat fusionné est normalisé à ce niveau avant
    l'export. `on_stage` nomme l'étape en cours et `should_cancel` permet d'interrompre : un export
    abandonné ne laisse qu'un fichier de sortie incomplet, le projet reste intact.
    """
    # Répartition de la barre de progression entre les étapes (fusion, normalisation éventuelle, encodage).
    merge_end, normalize_end = (0.3, 0.7) if normalize_lufs is not None else (0.4, 0.4)
    _stop_if_cancelled(should_cancel)
    _announce(on_stage, "Fusion des séquences")
    final_wav = merge_sequences(project, ffmpeg_service, sub_progress(on_progress, 0.0, merge_end))
    if normalize_lufs is not None:
        _stop_if_cancelled(should_cancel)
        _announce(on_stage, "Normalisation du volume")
        final_wav = _normalized_copy(
            ffmpeg_service,
            final_wav,
            Path(project.temp_dir) / "final_normalized.wav",
            normalize_lufs,
            sub_progress(on_progress, merge_end, normalize_end),
            should_cancel,
        )
    _stop_if_cancelled(should_cancel)
    _announce(on_stage, f"Encodage du fichier {fmt.upper()}")
    ffmpeg_service.export_audio(
        final_wav,
        out_path,
        fmt,
        quality,
        sub_progress(on_progress, normalize_end, 1.0),
        sample_rate=sample_rate,
        should_cancel=should_cancel,
    )


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\|?*\x00-\x1f]', "_", name).strip(" .") or "sequence"


def export_sequences_separately(
    project: Project,
    ffmpeg_service: FFmpegService,
    out_dir: str,
    fmt: str,
    quality: str,
    normalize_lufs: float | None = None,
    on_progress: ProgressCallback | None = None,
    sample_rate: int | None = None,
    on_stage: StageCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[str]:
    """Exporte chaque séquence (version traitée si disponible) dans son propre fichier, dans out_dir."""
    if not project.sequences:
        raise ExportError("Aucune séquence à exporter. Créez au moins une séquence.")

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    ordered = sorted(project.sequences, key=lambda s: s.order)
    written: list[str] = []
    for index, seq in enumerate(ordered, start=1):
        _stop_if_cancelled(should_cancel)
        _announce(on_stage, f"séquence {index} sur {len(ordered)} « {seq.name} »")
        slice_progress = sub_progress(on_progress, (index - 1) / len(ordered), index / len(ordered))
        encode_start = 0.5 if normalize_lufs is not None else 0.0
        target = directory / f"{index:02d}_{_safe_filename(seq.name)}.{fmt.lower()}"
        source = seq.effective_audio_path
        if normalize_lufs is not None:
            source = _normalized_copy(
                ffmpeg_service,
                source,
                Path(project.temp_dir) / f"export_norm_{seq.id}.wav",
                normalize_lufs,
                sub_progress(slice_progress, 0.0, 0.5),
                should_cancel,
            )
        ffmpeg_service.export_audio(
            source,
            str(target),
            fmt,
            quality,
            sub_progress(slice_progress, encode_start, 1.0),
            sample_rate=sample_rate,
            should_cancel=should_cancel,
        )
        written.append(str(target))
    return written
