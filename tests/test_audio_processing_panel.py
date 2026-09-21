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


def test_settings_are_disabled_without_sequence_but_the_window_stays_closable(qtbot, ffmpeg_binaries):
    panel = AudioProcessingPanel(FFmpegService(ffmpeg_binaries.ffmpeg_path))
    qtbot.addWidget(panel)

    assert not panel._settings_area.isEnabled()
    assert not panel._apply_button.isEnabled()
    assert panel._close_button.isEnabled() and panel._cancel_button.isEnabled()


def test_panel_enabled_and_loads_settings(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    sequence.audio_settings.gain = 4.0

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)

    assert panel._settings_area.isEnabled()
    assert panel._gain_slider.value() == 4.0


def test_selecting_profile_loads_preset_settings(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)

    panel._select_profile("Voix faible")

    assert panel._gain_slider.value() == 6.0
    assert panel._compression_toggle.isChecked()
    assert panel._normalize_toggle.isChecked()


def test_selecting_sequence_resets_profile_to_custom(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)
    panel._select_profile("Podcast")

    panel.set_sequence(sequence)

    assert panel._current_profile == "Personnalisé"


def test_apply_button_processes_sequence(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    panel.set_project(project)
    panel.set_sequence(sequence)
    panel._gain_slider.set_value(2.0)

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
    assert panel._apply_button.text() == "Appliquer à la séquence"

    panel.set_selected_sequences([first, second])
    assert panel._apply_button.text() == "Appliquer aux 2 séquences"
    assert "2 séquences sélectionnées" in panel._subtitle_label.text()

    panel._gain_slider.set_value(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()

    for sequence in (first, second):
        assert sequence.audio_settings.gain == 3.0
        assert sequence.processed_audio_path and Path(sequence.processed_audio_path).exists()
    assert first.audio_settings is not second.audio_settings
    assert panel._apply_button.isEnabled()


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

    panel._gain_slider.set_value(4.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    processed_path = sequence.processed_audio_path
    assert processed_path and sequence.audio_settings.gain == 4.0
    assert stack.count() == 1

    stack.undo()
    assert sequence.processed_audio_path == ""
    assert sequence.audio_settings.gain == 0.0
    assert panel._gain_slider.value() == 0.0

    stack.redo()
    assert sequence.processed_audio_path == processed_path
    assert sequence.audio_settings.gain == 4.0
    assert Path(processed_path).exists()
    assert panel._gain_slider.value() == 4.0


def test_second_processing_keeps_first_result_for_undo(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)

    panel._gain_slider.set_value(2.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    first_path = sequence.processed_audio_path

    panel._gain_slider.set_value(6.0)
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
    panel._gain_slider.set_value(3.0)
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

    panel._gain_slider.set_value(3.0)
    with qtbot.waitSignal(panel.processed, timeout=10000):
        panel._on_apply_clicked()
    assert stack.count() == 1

    stack.undo()
    assert first.processed_audio_path == "" and second.processed_audio_path == ""
    assert first.audio_settings.gain == 0.0 and second.audio_settings.gain == 0.0


def test_failed_processing_restores_previous_state_and_pushes_nothing(qtbot, project_with_sequence, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    project, sequence, ffmpeg_service = project_with_sequence
    panel, stack = _panel_with_undo(qtbot, project, sequence, ffmpeg_service)

    panel._gain_slider.set_value(5.0)
    panel._pending = ("x", [sequence], [panel._capture(sequence)])
    sequence.audio_settings = panel._read_settings()

    panel._on_processing_failed("boom")

    assert sequence.audio_settings.gain == 0.0
    assert stack.count() == 0
    assert panel._pending is None


# --- Réglages de la maquette -------------------------------------------------


def _panel(qtbot, ffmpeg_service):
    panel = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(panel)
    return panel


def test_noise_segment_aucune_turns_the_reduction_off(qtbot, project_with_sequence):
    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)

    panel._noise_segments.set_value("Aucune")
    assert panel._read_settings().noise_reduction is False

    panel._noise_segments.set_value("Forte")
    settings = panel._read_settings()
    assert settings.noise_reduction and settings.noise_reduction_level == "forte"


def test_a_disabled_reduction_still_shows_a_level_when_switched_back_on(qtbot, project_with_sequence):
    """« Aucune » ne doit pas laisser un niveau vide dans le modèle."""
    from app.models.audio_settings import AudioSettings

    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)

    panel._load_settings(AudioSettings(noise_reduction=False))

    assert panel._noise_segments.value() == "Aucune"
    assert panel._read_settings().noise_reduction_level in ("faible", "moyenne", "forte")


def test_fades_are_shown_in_milliseconds_and_stored_in_seconds(qtbot, project_with_sequence):
    from app.models.audio_settings import AudioSettings

    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)

    panel._load_settings(AudioSettings(fade_in=0.04, fade_out=0.12))
    assert (panel._fade_in_spin.value(), panel._fade_out_spin.value()) == (40, 120)

    panel._fade_in_spin.setValue(250)
    assert panel._read_settings().fade_in == pytest.approx(0.25)


def test_normalisation_mode_enables_only_the_matching_control(qtbot, project_with_sequence):
    from app.models.audio_settings import AudioSettings

    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)

    panel.set_sequence(_sequence)
    panel._load_settings(AudioSettings(normalize=True, normalize_mode="loudness"))
    assert panel._lufs_slider.isEnabled() and not panel._peak_spin.isEnabled()

    panel._peak_radio.setChecked(True)
    assert panel._peak_spin.isEnabled() and not panel._lufs_slider.isEnabled()
    assert panel._read_settings().normalize_mode == "peak"


def test_compression_ratio_and_threshold_reach_the_settings(qtbot, project_with_sequence):
    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)

    panel._compression_toggle.setChecked(True)
    panel._ratio_slider.set_value(4.0)
    panel._threshold_slider.set_value(-24.0)

    settings = panel._read_settings()
    assert settings.compression and settings.compression_ratio == pytest.approx(4.0)
    assert settings.compression_threshold_db == pytest.approx(-24.0)


def test_a_profile_fills_every_card(qtbot, project_with_sequence):
    _project, sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)
    panel.set_sequence(sequence)

    panel._profile_cards["Conférence"].clicked.emit("Conférence")

    assert panel._current_profile == "Conférence"
    assert panel._profile_cards["Conférence"].property("profile") == "true"
    settings = panel._read_settings()
    assert settings.eq_bass_db == pytest.approx(-3.0)
    assert settings.gain == pytest.approx(3.0)
    assert (panel._fade_in_spin.value(), panel._fade_out_spin.value()) == (40, 120)


def test_touching_a_setting_leaves_the_profile(qtbot, project_with_sequence):
    """Le profil ne décrit plus l'écran dès qu'un réglage est modifié à la main."""
    _project, sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)
    panel.set_sequence(sequence)
    panel._select_profile("Podcast")

    panel._gain_slider.slider.setValue(50)  # comme un déplacement à la souris, pas un chargement

    assert panel._current_profile == "Personnalisé"
    assert panel._profile_cards["Podcast"].property("profile") == "false"


def test_loading_a_profile_does_not_itself_leave_the_profile(qtbot, project_with_sequence):
    _project, sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)
    panel.set_sequence(sequence)

    panel._select_profile("Voix faible")

    assert panel._current_profile == "Voix faible"


def test_closing_is_requested_by_both_the_cross_and_cancel(qtbot, project_with_sequence):
    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = _panel(qtbot, ffmpeg_service)
    closed = []
    panel.close_requested.connect(lambda: closed.append(True))
    # Aucune séquence chargée : la fenêtre doit malgré tout pouvoir se fermer.

    panel._close_button.click()
    panel._cancel_button.click()

    assert closed == [True, True]


def test_the_dialog_closes_on_that_request(qtbot, project_with_sequence):
    from app.ui.processing_dialog import ProcessingDialog

    _project, _sequence, ffmpeg_service = project_with_sequence
    panel = AudioProcessingPanel(ffmpeg_service)
    dialog = ProcessingDialog(panel)
    qtbot.addWidget(dialog)
    dialog.show()

    panel.close_requested.emit()

    assert not dialog.isVisible()
