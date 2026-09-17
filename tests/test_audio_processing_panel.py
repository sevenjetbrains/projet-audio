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
