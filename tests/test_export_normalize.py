"""Tests de la normalisation optionnelle du volume à l'export."""

import wave
from pathlib import Path

import numpy as np
import pytest

from app.models.media import MediaInfo
from app.services import sequence_service
from app.services.export_service import export_project, export_sequences_separately
from app.services.ffmpeg_service import FFmpegService
from app.services.project_service import create_project_for_video
from app.ui.export_dialog import ExportDialog

_RATE = 16000


def _rms(path: str) -> float:
    with wave.open(path, "rb") as wav_file:
        samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples**2)))


@pytest.fixture
def quiet_project(ffmpeg_binaries):
    """Projet dont l'audio (6 s de tonalité à très faible niveau) est nettement sous -16 LUFS."""
    t = np.arange(int(_RATE * 6.0)) / _RATE
    samples = (0.01 * np.sin(2 * np.pi * 300 * t) * 32767).astype(np.int16)
    media_info = MediaInfo(
        path="quiet.mp4", duration=6.0, container_format="mp4", video_codec="h264",
        audio_codec="aac", sample_rate=_RATE, channels=1, resolution=None, bitrate=None, size_bytes=1,
    )
    project = create_project_for_video(media_info)
    wav_path = Path(project.temp_dir) / "source.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_RATE)
        wav_file.writeframes(samples.tobytes())
    project.original_audio_path = str(wav_path)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 3.0)
    sequence_service.add_sequence(project, ffmpeg_service, 3.0, 6.0)
    return project, ffmpeg_service


def test_export_without_normalization_keeps_level(quiet_project, tmp_path):
    project, ffmpeg_service = quiet_project
    out = tmp_path / "plain.wav"

    export_project(project, ffmpeg_service, str(out), "WAV", "16")

    assert _rms(str(out)) == pytest.approx(_rms(project.original_audio_path), rel=0.1)


def test_export_with_normalization_raises_quiet_audio(quiet_project, tmp_path):
    project, ffmpeg_service = quiet_project
    plain, normalized = tmp_path / "plain.wav", tmp_path / "normalized.wav"

    export_project(project, ffmpeg_service, str(plain), "WAV", "16")
    export_project(project, ffmpeg_service, str(normalized), "WAV", "16", normalize_lufs=-16.0)

    assert _rms(str(normalized)) > 3 * _rms(str(plain))


def test_normalization_does_not_modify_project_audio(quiet_project, tmp_path):
    project, ffmpeg_service = quiet_project
    before = [(seq.audio_path, Path(seq.audio_path).read_bytes()) for seq in project.sequences]

    export_project(project, ffmpeg_service, str(tmp_path / "n.wav"), "WAV", "16", normalize_lufs=-16.0)

    assert [(seq.audio_path, Path(seq.audio_path).read_bytes()) for seq in project.sequences] == before


def test_separate_export_with_normalization(quiet_project, tmp_path):
    project, ffmpeg_service = quiet_project

    plain = export_sequences_separately(project, ffmpeg_service, str(tmp_path / "plain"), "WAV", "16")
    normalized = export_sequences_separately(
        project, ffmpeg_service, str(tmp_path / "norm"), "WAV", "16", normalize_lufs=-16.0
    )

    assert len(normalized) == 2
    assert all(_rms(n) > 3 * _rms(p) for p, n in zip(plain, normalized))


def test_dialog_passes_normalization_setting_to_export(qtbot, quiet_project, monkeypatch, tmp_path):
    project, ffmpeg_service = quiet_project
    calls = []
    # La fenêtre référence la fonction directement : c'est là qu'il faut la remplacer.
    monkeypatch.setattr(
        "app.ui.export_dialog.export_project",
        lambda *args, **kwargs: calls.append((args[3:], kwargs)) or None,
    )
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dialog = ExportDialog(project, ffmpeg_service)
    qtbot.addWidget(dialog)
    assert not dialog._lufs_spin.isEnabled()

    dialog._path_edit.setText(str(tmp_path / "out.wav"))
    dialog._on_export_clicked()
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=5000)
    assert calls[-1][0][-1] is None  # case décochée : aucune normalisation demandée

    dialog._normalize_cb.setChecked(True)
    assert dialog._lufs_spin.isEnabled()
    dialog._lufs_spin.setValue(-20.0)
    dialog._export_button.setEnabled(True)
    dialog._on_export_clicked()
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=5000)

    assert calls[-1][0][-1] == -20.0
