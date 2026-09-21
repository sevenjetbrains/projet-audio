"""Dates et délais en français, pour l'écran d'accueil (« hier à 18:24 », « il y a 3 min »).

Distinct de `time_utils`, qui formate des durées d'audio (timecodes) et non des
moments du calendrier.
"""

from datetime import datetime, timedelta
from pathlib import Path

# Abréviations de mois telles qu'on les écrit en français (mai, juin et juillet exceptés).
_MONTHS = (
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
)

_ZERO = timedelta(0)  # une horloge décalée ne doit pas produire « il y a -2 min »


def format_moment(moment: datetime, now: datetime | None = None) -> str:
    """« aujourd'hui à 09:12 », « hier à 18:24 », « 17 sept. à 09:51 » selon l'ancienneté."""
    reference = now or datetime.now()
    days = (reference.date() - moment.date()).days
    clock = f"{moment.hour:02d}:{moment.minute:02d}"
    if days == 0:
        return f"aujourd'hui à {clock}"
    if days == 1:
        return f"hier à {clock}"
    day = f"{moment.day} {_MONTHS[moment.month - 1]}"
    if moment.year != reference.year:
        day += f" {moment.year}"
    return f"{day} à {clock}"


def format_elapsed(moment: datetime, now: datetime | None = None) -> str:
    """« à l'instant », « il y a 3 min », « il y a 2 h », « il y a 4 j » — ancienneté approchée."""
    seconds = max((now or datetime.now()) - moment, _ZERO).total_seconds()
    if seconds < 60:
        return "à l'instant"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    return f"il y a {hours // 24} j"


def format_folder(file_path: str) -> str:
    """Dossier contenant le fichier, le dossier personnel abrégé en `~`, avec un séparateur final."""
    folder = Path(file_path).parent
    try:
        folder = Path("~") / folder.relative_to(Path.home())
    except ValueError:
        pass  # hors du dossier personnel : chemin absolu tel quel
    return folder.as_posix().rstrip("/") + "/"
