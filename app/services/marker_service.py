"""Repères (marqueurs) d'un Project : des instants nommés posés sur la timeline source.

Un repère ne touche à aucun fichier : poser, retirer ou renommer se résume à une
manipulation de `project.markers`, donc à une opération réversible telle quelle
(§17/§34) — pas besoin du découpage en deux étapes utilisé pour les séquences.
La liste est maintenue triée par position : c'est l'ordre d'affichage comme celui
de la navigation d'un repère à l'autre.
"""

from typing import NamedTuple
from uuid import uuid4

from app.models.marker import Marker
from app.models.project import Project

# Deux repères plus proches que cela seraient confondus à l'écran comme à l'oreille.
MIN_GAP_SECONDS = 0.05


class MarkerInterval(NamedTuple):
    """Tranche d'audio délimitée par deux repères ; `label` est celui du repère qui l'ouvre."""

    start: float
    end: float
    label: str = ""


def create_marker(project: Project, position: float, label: str | None = None) -> Marker:
    """Construit un repère (non rattaché au projet) à `position`, nommé « Repère N » par défaut."""
    return Marker(
        id=uuid4().hex[:8],
        position=max(position, 0.0),
        label=label or f"Repère {len(project.markers) + 1}",
    )


def insert_marker(project: Project, marker: Marker) -> None:
    """Rattache un repère au projet, à sa place dans l'ordre chronologique."""
    project.markers.append(marker)
    project.markers.sort(key=lambda m: m.position)


def remove_marker(project: Project, marker_id: str) -> Marker:
    """Retire le repère et le retourne, pour qu'un undo puisse le réinsérer tel quel."""
    marker = find(project, marker_id)
    project.markers.remove(marker)
    return marker


def rename_marker(project: Project, marker_id: str, label: str) -> None:
    find(project, marker_id).label = label


def move_marker(project: Project, marker_id: str, position: float) -> None:
    """Déplace un repère dans le temps ; la liste reste triée."""
    find(project, marker_id).position = max(position, 0.0)
    project.markers.sort(key=lambda m: m.position)


def find(project: Project, marker_id: str) -> Marker:
    for marker in project.markers:
        if marker.id == marker_id:
            return marker
    raise KeyError(f"Repère introuvable : {marker_id}")


def marker_near(project: Project, position: float, tolerance: float = MIN_GAP_SECONDS) -> Marker | None:
    """Repère le plus proche de `position`, s'il est à moins de `tolerance` secondes."""
    candidates = [m for m in project.markers if abs(m.position - position) <= tolerance]
    if not candidates:
        return None
    return min(candidates, key=lambda m: abs(m.position - position))


def next_marker(project: Project, position: float) -> Marker | None:
    """Premier repère strictement après `position` (à la tolérance près), ou None."""
    for marker in sorted(project.markers, key=lambda m: m.position):
        if marker.position > position + MIN_GAP_SECONDS:
            return marker
    return None


def previous_marker(project: Project, position: float) -> Marker | None:
    """Dernier repère strictement avant `position` (à la tolérance près), ou None."""
    for marker in sorted(project.markers, key=lambda m: m.position, reverse=True):
        if marker.position < position - MIN_GAP_SECONDS:
            return marker
    return None


def surrounding_range(project: Project, position: float, duration: float) -> tuple[float, float] | None:
    """Intervalle entre les deux repères qui encadrent `position`.

    Les bords du fichier (0 et `duration`) tiennent lieu de repère manquant, de sorte
    qu'un unique repère découpe déjà l'audio en deux intervalles exploitables. Retourne
    None s'il n'y a aucun repère, ou si l'intervalle obtenu est vide.
    """
    if not project.markers:
        return None
    before = previous_marker(project, position)
    after = next_marker(project, position)
    start = before.position if before is not None else 0.0
    end = after.position if after is not None else duration
    if end - start < MIN_GAP_SECONDS:
        return None
    return start, end


def intervals(project: Project, duration: float) -> list[MarkerInterval]:
    """Découpe l'audio à chaque repère : [0, r1], [r1, r2], …, [rN, durée].

    Chaque tranche porte le nom du repère qui l'ouvre — celle qui précède le premier
    repère n'en a pas. Les tranches trop courtes (deux repères collés, un repère sur un
    bord) sont écartées : elles ne donneraient pas une séquence exploitable.
    """
    positions = [marker.position for marker in sorted(project.markers, key=lambda m: m.position)]
    labels = [marker.label for marker in sorted(project.markers, key=lambda m: m.position)]
    edges = [0.0] + positions + [duration]
    opening_labels = [""] + labels
    return [
        MarkerInterval(start, end, label)
        for start, end, label in zip(edges, edges[1:], opening_labels)
        if end - start >= MIN_GAP_SECONDS
    ]
