"""Fixtures partagées : génère une courte vidéo/wav de test."""

import subprocess
import wave

import numpy as np
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


@pytest.fixture(scope="session")
def synthetic_wav_file(tmp_path_factory):
    """WAV mono 16-bit de 2s (tonalité 440Hz) généré directement, sans ffmpeg."""
    framerate = 8000
    t = np.linspace(0, 2, framerate * 2, endpoint=False)
    samples = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)

    out_dir = tmp_path_factory.mktemp("synthetic_wav")
    out_path = out_dir / "synthetic.wav"
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(framerate)
        wav_file.writeframes(samples.tobytes())

    return str(out_path)


@pytest.fixture(autouse=True)
def _no_blocking_save_prompt(monkeypatch):
    """La fermeture d'une fenêtre « modifiée » ouvre une QMessageBox modale : elle bloquerait les tests.

    Par défaut on répond « Ne pas enregistrer » ; un test qui vérifie ce dialogue le remplace lui-même.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
