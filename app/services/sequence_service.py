"""Gestion du cycle de vie des séquences d'un Project (CRUD + ordre).

Les opérations sont scindées en deux étapes pour permettre l'undo/redo (§17/§34) :
- `create_sequence` / `create_duplicate` : effectue le découpage/copie ffmpeg (coûteux,
  fait une seule fois) et retourne l'objet Sequence, SANS le rattacher au projet.
- `insert_sequence` / `remove_sequence_from_list` : ajoute/retire l'objet de
  `project.sequences` (pure manipulation de liste, réversible sans re-toucher le disque).
`add_sequence`/`duplicate_sequence`/`remove_sequence` combinent les deux étapes pour
les appelants qui n'ont pas besoin d'annulation (chargement de projet, tests).
"""

import shutil
from pathlib import Path
from uuid import uuid4

from app.models.project import Project
from app.models.sequence import Sequence
from app.services.ffmpeg_service import FFmpegService


def create_sequence(
    project: Project,
    ffmpeg_service: FFmpegService,
    start: float,
    end: float,
    name: str | None = None,
) -> Sequence:
    """Découpe [start, end] de l'audio source et construit la Sequence (non rattachée)."""
    if end <= start:
        raise ValueError("end must be greater than start")

    sequence_id = uuid4().hex[:8]
    out_path = str(Path(project.temp_dir) / f"seq_{sequence_id}.wav")
    ffmpeg_service.cut_audio(project.original_audio_path, out_path, start, end)

    return Sequence(
        id=sequence_id,
        name=name or f"Séquence {len(project.sequences) + 1}",
        source_start=start,
        source_end=end,
        order=-1,
        audio_path=out_path,
    )


def create_duplicate(project: Project, sequence_id: str) -> Sequence:
    """Copie le fichier audio d'une séquence existante et construit la copie (non rattachée)."""
    source = _find(project, sequence_id)
    new_id = uuid4().hex[:8]
    out_path = str(Path(project.temp_dir) / f"seq_{new_id}.wav")
    shutil.copyfile(source.audio_path, out_path)

    return Sequence(
        id=new_id,
        name=f"{source.name} (copie)",
        source_start=source.source_start,
        source_end=source.source_end,
        order=-1,
        audio_path=out_path,
    )


def insert_sequence(project: Project, sequence: Sequence, index: int | None = None) -> None:
    """Rattache une Sequence déjà construite à project.sequences (à `index`, ou en fin de liste)."""
    if index is None or index >= len(project.sequences):
        project.sequences.append(sequence)
    else:
        project.sequences.insert(index, sequence)
    _reindex(project)


def remove_sequence_from_list(project: Project, sequence_id: str) -> tuple[Sequence, int]:
    """Retire une Sequence de la liste SANS supprimer son fichier (réversible). Retourne (sequence, ancien_index)."""
    sequence = _find(project, sequence_id)
    index = project.sequences.index(sequence)
    project.sequences.remove(sequence)
    _reindex(project)
    return sequence, index


def add_sequence(
    project: Project,
    ffmpeg_service: FFmpegService,
    start: float,
    end: float,
    name: str | None = None,
) -> Sequence:
    """Découpe et ajoute directement la séquence au projet (sans étape d'annulation)."""
    sequence = create_sequence(project, ffmpeg_service, start, end, name)
    insert_sequence(project, sequence)
    return sequence


def remove_sequence(project: Project, sequence_id: str) -> None:
    """Retire une séquence du projet et supprime définitivement son fichier audio."""
    sequence, _index = remove_sequence_from_list(project, sequence_id)
    Path(sequence.audio_path).unlink(missing_ok=True)


def duplicate_sequence(project: Project, sequence_id: str) -> Sequence:
    """Duplique et ajoute directement la copie au projet (sans étape d'annulation)."""
    duplicate = create_duplicate(project, sequence_id)
    insert_sequence(project, duplicate)
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
