"""Calculs purs pour la suppression des silences (aucune dépendance ffmpeg/Qt).

La détection elle-même (analyse du niveau audio) est déléguée à FFmpeg
(`silencedetect`, exécuté par FFmpegService.detect_silences) qui produit une
liste d'intervalles (start, end) en secondes. Ce module ne fait que la
géométrie des intervalles : réduire chaque silence d'une marge à conserver,
puis calculer le complément (segments à garder).
"""


def compute_keep_ranges(
    silences: list[tuple[float, float]],
    total_duration: float,
    keep_padding: float = 0.0,
) -> list[tuple[float, float]]:
    """Retourne les segments à conserver (complément des silences, réduits de `keep_padding`)."""
    shrunk = []
    for start, end in silences:
        shrunk_start = start + keep_padding
        shrunk_end = end - keep_padding
        if shrunk_end > shrunk_start:
            shrunk.append((shrunk_start, shrunk_end))

    keep_ranges = []
    cursor = 0.0
    for start, end in shrunk:
        if start > cursor:
            keep_ranges.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_duration:
        keep_ranges.append((cursor, total_duration))

    return [(a, b) for a, b in keep_ranges if b > a]
