"""Smoke test + export réel pour ExportDialog."""

from pathlib import Path

import pytest

from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui.export_dialog import ExportDialog


@pytest.fixture
def project_with_sequence(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.5)

    return project, ffmpeg_service


def test_export_dialog_instantiates(qtbot, project_with_sequence):
    project, ffmpeg_service = project_with_sequence
    dialog = ExportDialog(project, ffmpeg_service)
    qtbot.addWidget(dialog)

    assert dialog._format_combo.count() == 6


def test_export_dialog_runs_export_to_wav(qtbot, project_with_sequence, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    project, ffmpeg_service = project_with_sequence
    dialog = ExportDialog(project, ffmpeg_service)
    qtbot.addWidget(dialog)

    out_path = tmp_path / "result.wav"
    dialog._path_edit.setText(str(out_path))
    dialog._on_export_clicked()

    # Attend la fin réelle du traitement (signal traité), pas juste l'existence du fichier,
    # pour éviter qu'un worker encore actif ne délivre son signal après la destruction du widget.
    qtbot.waitUntil(lambda: "terminé" in dialog._status_label.text().lower(), timeout=5000)
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=2000)

    assert out_path.exists()


def test_export_dialog_separate_files(qtbot, project_with_sequence, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    project, ffmpeg_service = project_with_sequence
    dialog = ExportDialog(project, ffmpeg_service)
    qtbot.addWidget(dialog)

    dialog._separate_cb.setChecked(True)
    dialog._path_edit.setText(str(tmp_path / "seqs"))
    dialog._on_export_clicked()

    qtbot.waitUntil(lambda: "terminé" in dialog._status_label.text().lower(), timeout=5000)
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=2000)

    assert len(list((tmp_path / "seqs").glob("*.wav"))) == 1
