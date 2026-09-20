"""Formatage et lecture de durées pour l'affichage.

`format_timecode` (HH:MM:SS.mmm) reste le format « technique » utilisé par les
services et les noms de fichiers ; les variantes à virgule servent à l'interface,
qui suit la convention décimale française.
"""

import re

_TIMECODE_PATTERN = re.compile(
    r"^\s*(?:(?:(?P<h>\d+):)?(?P<m>\d{1,2}):)?(?P<s>\d{1,2})(?:[.,](?P<ms>\d{1,3}))?\s*$"
)


def _split(seconds: float) -> tuple[int, int, int, int]:
    """Décompose des secondes en (heures, minutes, secondes, millièmes), arrondies au millième."""
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return hours, minutes, secs, ms


def format_timecode(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")

    hours, minutes, secs, ms = _split(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def format_timecode_fr(seconds: float) -> str:
    """`HH:MM:SS,mmm` : comme `format_timecode`, avec la virgule décimale française."""
    hours, minutes, secs, ms = _split(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_clock(seconds: float, decimals: int = 3) -> str:
    """Timecode compact `MM:SS,mmm` pour les colonnes étroites ; les heures n'apparaissent qu'au besoin.

    `decimals` fixe le nombre de chiffres après la virgule (3 = millièmes, 2 = centièmes, 0 = aucun).
    """
    hours, minutes, secs, ms = _split(seconds)
    head = f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
    if decimals <= 0:
        return head
    return f"{head},{ms:03d}"[: len(head) + 1 + decimals]


def parse_timecode(text: str) -> float | None:
    """Secondes lues depuis `SS`, `MM:SS`, `HH:MM:SS`, avec millièmes optionnels ; None si illisible."""
    match = _TIMECODE_PATTERN.match(text)
    if match is None:
        return None
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s"))
    ms_text = match.group("ms") or ""
    milliseconds = int(ms_text.ljust(3, "0")) if ms_text else 0
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
