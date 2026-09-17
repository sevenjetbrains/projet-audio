"""Helpers fichiers/chemins."""

from pathlib import Path


def is_supported_video(path: str, supported_extensions: tuple[str, ...]) -> bool:
    return Path(path).suffix.lower() in supported_extensions
