"""Gestion du cycle de vie des séquences d'un Project (CRUD + ordre).

Les opérations sont scindées en deux étapes pour permettre l'undo/redo (§17/§34) :
- `create_sequence` / `create_duplicate` : effectue le découpage/copie ffmpeg (coûteux,
  fait une seule fois) et retourne l'objet Sequence, SANS le rattacher au projet.
- `insert_sequence` / `remove_sequence_from_list` : ajoute/retire l'objet de
  `project.sequences` (pure manipulation de liste, réversible sans re-toucher le disque).
`add_sequence`/`duplicate_sequence`/`remove_sequence` combinent les deux étapes pour
les appelants qui n'ont pas besoin d'annulation (chargement de projet, tests).
"""

import copy
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.audio.silence_detection import compute_keep_ranges
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import audio_processor
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



# --- Édition d'une séquence existante : nouvelles bornes, division ----------------------------------------

MIN_SEQUENCE_SECONDS = 0.05  # en dessous, une séquence n'aurait plus de contenu audible


def _derive(project: Project, ffmpeg_service: FFmpegService, model: Sequence, start: float, end: float, name: str) -> Sequence:
    """Nouvelle séquence découpée dans la source, qui garde les réglages de traitement de `model` (et les réapplique)."""
    derived = create_sequence(project, ffmpeg_service, start, end, name=name)
    derived.audio_settings = copy.deepcopy(model.audio_settings)
    # Sans cela, un traitement déjà appliqué (bruit, normalisation, silences…) disparaîtrait en silence à la fusion.
    audio_processor.process_sequence(project, derived, ffmpeg_service)
    return derived


def _check_bounds(project: Project, start: float, end: float) -> None:
    if end - start < MIN_SEQUENCE_SECONDS:
        raise ValueError(f"Une séquence doit durer au moins {MIN_SEQUENCE_SECONDS * 1000:.0f} ms.")
    if start < 0:
        raise ValueError("Le début de la séquence ne peut pas être négatif.")
    duration = project.source_video.duration if project.source_video is not None else None
    if duration is not None and end > duration + 0.01:
        raise ValueError("La fin de la séquence dépasse la durée de la vidéo.")


def retime_sequence(
    project: Project, ffmpeg_service: FFmpegService, sequence_id: str, start: float, end: float
) -> tuple[Sequence, Sequence]:
    """Prépare une version de la séquence aux nouvelles bornes. Retourne (ancienne, nouvelle), sans rien modifier.

    La nouvelle garde l'identifiant, le nom, la place et les réglages de traitement ; son audio est redécoupé dans
    la source. L'appelant l'échange avec l'ancienne par `replace_sequences` (annulable : les deux fichiers subsistent).
    """
    old = _find(project, sequence_id)
    _check_bounds(project, start, end)
    if abs(start - old.source_start) < 1e-6 and abs(end - old.source_end) < 1e-6:
        raise ValueError("Les bornes de la séquence n'ont pas changé.")
    new = _derive(project, ffmpeg_service, old, start, end, old.name)
    new.id = old.id
    new.order = old.order
    return old, new


def split_sequence(
    project: Project, ffmpeg_service: FFmpegService, sequence_id: str, at: float
) -> tuple[Sequence, list[Sequence]]:
    """Prépare la division d'une séquence en deux au temps `at` (temps de la source). Retourne (ancienne, [a, b])."""
    old = _find(project, sequence_id)
    if not (old.source_start + MIN_SEQUENCE_SECONDS <= at <= old.source_end - MIN_SEQUENCE_SECONDS):
        raise ValueError("La tête de lecture doit se trouver à l'intérieur de la séquence à diviser.")
    first = _derive(project, ffmpeg_service, old, old.source_start, at, f"{old.name} (1)")
    second = _derive(project, ffmpeg_service, old, at, old.source_end, f"{old.name} (2)")
    return old, [first, second]


def replace_sequences(project: Project, remove_ids: list[str], add: list[Sequence]) -> None:
    """Remplace des séquences par d'autres, à la place de la première retirée (réversible en échangeant les rôles)."""
    indexes = [project.sequences.index(_find(project, sequence_id)) for sequence_id in remove_ids]
    position = min(indexes)
    for sequence_id in remove_ids:
        project.sequences.remove(_find(project, sequence_id))
    for offset, sequence in enumerate(add):
        project.sequences.insert(position + offset, sequence)
    _reindex(project)


def _find(project: Project, sequence_id: str) -> Sequence:
    for sequence in project.sequences:
        if sequence.id == sequence_id:
            return sequence
    raise KeyError(f"Sequence introuvable : {sequence_id}")


def _reindex(project: Project) -> None:
    for index, sequence in enumerate(project.sequences):
        sequence.order = index


@dataclass
class AutoSplitParams:
    """Réglages du découpage automatique : la parole est ce qui reste entre les silences."""

    threshold_db: float = -35.0
    min_silence: float = 0.5
    keep_padding: float = 0.1
    min_segment: float = 0.5


def detect_speech_ranges(
    project: Project, ffmpeg_service: FFmpegService, params: AutoSplitParams
) -> list[tuple[float, float]]:
    """Segments non silencieux de l'audio source, en écartant ceux plus courts que `min_segment`."""
    if project.source_video is None or not project.original_audio_path:
        raise ValueError("Aucun audio source à analyser.")

    silences = ffmpeg_service.detect_silences(project.original_audio_path, params.threshold_db, params.min_silence)
    ranges = compute_keep_ranges(silences, project.source_video.duration, params.keep_padding)
    return [(start, end) for start, end in ranges if end - start >= params.min_segment]


def create_sequences_from_ranges(
    project: Project,
    ffmpeg_service: FFmpegService,
    ranges: list[tuple[float, float]],
    names: list[str] | None = None,
) -> list[Sequence]:
    """Découpe l'audio source selon les segments donnés (non rattachées au projet).

    `names` nomme les segments un à un (un nom vide ou absent retombe sur la numérotation
    à la suite) : le découpage aux repères reprend ainsi le nom du repère qui ouvre chaque
    tranche, au lieu de « Séquence 7 »."""
    first_number = len(project.sequences) + 1
    return [
        create_sequence(
            project,
            ffmpeg_service,
            start,
            end,
            name=(names[index] if names and index < len(names) else "") or f"Séquence {first_number + index}",
        )
        for index, (start, end) in enumerate(ranges)
    ]


def create_sequences_from_silences(
    project: Project, ffmpeg_service: FFmpegService, params: AutoSplitParams
) -> list[Sequence]:
    """Détecte les passages puis les découpe en séquences (non rattachées au projet)."""
    return create_sequences_from_ranges(project, ffmpeg_service, detect_speech_ranges(project, ffmpeg_service, params))
