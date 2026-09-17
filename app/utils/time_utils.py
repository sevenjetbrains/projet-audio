"""Formatage de durées pour l'affichage (HH:MM:SS.mmm)."""


def format_timecode(seconds: float) -> str:
    if seconds < 0:
        raise ValueError("seconds must be non-negative")

    total_ms = round(seconds * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
