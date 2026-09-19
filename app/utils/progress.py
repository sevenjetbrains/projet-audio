"""Suivi de progression composable : une opération longue rapporte une fraction 0..1 à un callback."""

from collections.abc import Callable

ProgressCallback = Callable[[float], None]


def sub_progress(callback: ProgressCallback | None, start: float, end: float) -> ProgressCallback | None:
    """Callback qui projette une progression 0..1 sur la tranche [start, end] de la progression parente."""
    if callback is None:
        return None

    def report(fraction: float) -> None:
        callback(start + (end - start) * max(0.0, min(1.0, fraction)))

    return report
