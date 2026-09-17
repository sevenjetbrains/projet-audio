"""Fixtures partagées : génère une courte vidéo de test avec ffmpeg (lavfi)."""

import subprocess

import pytest

from app.config.settings import find_ffmpeg_binaries


@pytest.fixture(scope="session")
def ffmpeg_binaries():
    return find_ffmpeg_binaries()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory, ffmpeg_binaries):
    """Vidéo MP4 d'1 seconde (mire + tonalité 1kHz) générée localement pour les tests."""
    out_dir = tmp_path_factory.mktemp("sample_media")
    out_path = out_dir / "sample.mp4"

    subprocess.run(
        [
            ffmpeg_binaries.ffmpeg_path,
            "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
            "-c:v", "libx264", "-c:a", "aac",
            "-shortest",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return str(out_path)
