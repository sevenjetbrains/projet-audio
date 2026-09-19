"""Tests de AudioProcessingPanel (smoke + application réelle d'un traitement)."""

from pathlib import Path

import pytest

from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui.audio_processing_panel import AudioProcessingPanel


@pytest.fixture
def project_with_sequence(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    sequence = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.8)
    return project, sequence, ffmpeg_service


def test_panel_disabled_without_sequence(qtbot, ffmpeg_binaries):
    panel = AudioProcessingPanel(FFmpegService(ffmpeg_binaries.ffmpeg_path))
    qtbot.addWidget(panel)

    assert not panel.isEnabled()


def test_panel_enabled_and_loads_settings(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    sequence.audio_settings.gain = 4.0

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)

    assert panel.isEnabled()
    assert panel._gain_spin.value() == 4.0


def test_selecting_profile_loads_preset_settings(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)

    panel._profile_combo.setCurrentText("Voix faible")

    assert panel._gain_spin.value() == 6.0
    assert panel._compression_cb.isChecked()
    assert panel._normalize_cb.isChecked()


def test_selecting_sequence_resets_profile_to_custom(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)
    panel._profile_combo.setCurrentText("Podcast")

    panel.set_sequence(sequence)

    assert panel._profile_combo.currentText() == "Personnalisé"


def test_apply_button_processes_sequence(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)
    panel._gain_spin.setValue(2.0)

    with qtbot.waitSignal(panel.processed, timeout=5000):
        panel._on_apply_clicked()

    assert sequence.processed_audio_path
    assert Path(sequence.processed_audio_path).exists()


def test_apply_to_selection_processes_all_selected_sequences(qtbot, project_with_sequence):
    project, first, ffmpeg_service = project_with_sequence
    second = sequence_service.add_sequence(project, ffmpeg_service, 0.1, 0.5)

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(first)

    panel.set_selected_sequences([first])
    assert not panel._apply_selection_button.isEnabled()

    panel.set_selected_sequences([first, second])
    assert panel._apply_selection_button.isEnabled()
    assert "(2)" in panel._apply_selection_button.text()

    panel._gain_spin.setValue(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_selection_clicked()

    for sequence in (first, second):
        assert sequence.audio_settings.gain == 3.0
        assert sequence.processed_audio_path and Path(sequence.processed_audio_path).exists()
    assert first.audio_settings is not second.audio_settings
    assert panel._apply_selection_button.isEnabled()


def _panel_with_undo(qtbot, project, sequence, ffmpeg_service):
    from PySide6.QtGui import QUndoStack

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    stack = QUndoStack(panel)
    panel.set_undo_stack(stack)
    panel.set_project(project)
    panel.set_sequence(sequence)
    return panel, stack


def test_processing_is_undoable_and_redoable(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)

    panel._gain_spin.setValue(4.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    processed_path = sequence.processed_audio_path
    assert processed_path and sequence.audio_settings.gain == 4.0
    assert stack.count() == 1

    stack.undo()
    assert sequence.processed_audio_path == ""
    assert sequence.audio_settings.gain == 0.0
    assert panel._gain_spin.value() == 0.0

    stack.redo()
    assert sequence.processed_audio_path == processed_path
    assert sequence.audio_settings.gain == 4.0
    assert Path(processed_path).exists()
    assert panel._gain_spin.value() == 4.0


def test_second_processing_keeps_first_result_for_undo(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)

    panel._gain_spin.setValue(2.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    first_path = sequence.processed_audio_path

    panel._gain_spin.setValue(6.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    second_path = sequence.processed_audio_path
    assert second_path != first_path

    stack.undo()
    assert sequence.processed_audio_path == first_path
    assert sequence.audio_settings.gain == 2.0
    assert Path(first_path).exists()


def test_reset_is_undoable(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)
    panel._gain_spin.setValue(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    processed_path = sequence.processed_audio_path

    panel._on_reset_clicked()
    assert sequence.processed_audio_path == ""
    assert sequence.audio_settings.gain == 0.0

    stack.undo()
    assert sequence.processed_audio_path == processed_path
    assert sequence.audio_settings.gain == 3.0


def test_batch_processing_is_a_single_undo_step(qtbot, project_with_sequence):
    project, first, ffmpeg_service = project_with_sequence
    second = sequence_service.add_sequence(project, ffmpeg_service, 0.1, 0.5)
    panel, stack = _panel_with_undo(qtbot, project, first, ffmpeg_service)
    panel.set_selected_sequences([first, second])

    panel._gain_spin.setValue(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_selection_clicked()
    assert stack.count() == 1

    stack.undo()
    assert first.processed_audio_path == "" and second.processed_audio_path == ""
    assert first.audio_settings.gain == 0.0 and second.audio_settings.gain == 0.0


def test_failed_processing_restores_previous_state_and_pushes_nothing(qtbot, project_with_sequence, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)

    panel._gain_spin.setValue(5.0)
    panel._pending = ("x", [sequence], [panel._capture(sequence)])
    sequence.audio_settings = panel._read_settings()

    panel._on_processing_failed("boom")

    assert sequence.audio_settings.gain == 0.0
    assert stack.count() == 0
    assert panel._pending is None
