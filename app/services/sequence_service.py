"""Gestion du cycle de vie des séquences d'un Project (CRUD + ordre)."""

import shutil
from pathlib import Path
from uuid import uuid4

from app.models.project import Project
from app.models.sequence import Sequence
from app.services.ffmpeg_service import FFmpegService


def add_sequence(
    project: Project,
    ffmpeg_service: FFmpegService,
    start: float,
    end: float,
    name: str | None = None,
) -> Sequence:
    """Découpe [start, end] de l'audio source et ajoute la séquence au projet."""
    if end <= start:
        raise ValueError("end must be greater than start")

    sequence_id = uuid4().hex[:8]
    order = len(project.sequences)
    out_path = str(Path(project.temp_dir) / f"seq_{sequence_id}.wav")

    ffmpeg_service.cut_audio(project.original_audio_path, out_path, start, end)

    sequence = Sequence(
        id=sequence_id,
        name=name or f"Séquence {order + 1}",
        source_start=start,
        source_end=end,
        order=order,
        audio_path=out_path,
    )
    project.sequences.append(sequence)
    return sequence


def remove_sequence(project: Project, sequence_id: str) -> None:
    sequence = _find(project, sequence_id)
    project.sequences.remove(sequence)
    Path(sequence.audio_path).unlink(missing_ok=True)
    _reindex(project)


def duplicate_sequence(project: Project, sequence_id: str) -> Sequence:
    source = _find(project, sequence_id)
    new_id = uuid4().hex[:8]
    out_path = str(Path(project.temp_dir) / f"seq_{new_id}.wav")
    shutil.copyfile(source.audio_path, out_path)

    duplicate = Sequence(
        id=new_id,
        name=f"{source.name} (copie)",
        source_start=source.source_start,
        source_end=source.source_end,
        order=len(project.sequences),
        audio_path=out_path,
    )
    project.sequences.append(duplicate)
    return duplicate


def rename_sequence(project: Project, sequence_id: str, new_name: str) -> None:
    sequence = _find(project, sequence_id)
    sequence.name = new_name


def reorder_sequences(project: Project, ordered_ids: list[str]) -> None:
    """Réordonne project.sequences selon la liste d'ids donnée, réassigne .order."""
    by_id = {seq.id: seq for seq in project.sequences}
    if set(by_id) != set(ordered_ids):
        raise ValueError("ordered_ids must contain exactly the current sequence ids")

    project.sequences = [by_id[seq_id] for seq_id in ordered_ids]
    _reindex(project)


def _find(project: Project, sequence_id: str) -> Sequence:
    for sequence in project.sequences:
        if sequence.id == sequence_id:
            return sequence
    raise KeyError(f"Sequence introuvable : {sequence_id}")


def _reindex(project: Project) -> None:
    for index, sequence in enumerate(project.sequences):
        sequence.order = index
