"""Tests de la fenêtre « Fusion et export » : fusion, format, aperçu, progression, annulation."""

from pathlib import Path

import numpy as np
import pytest

from app.models.audio_settings import AudioSettings
from app.services import sequence_service
from app.services.export_service import export_project, export_sequences_separately
from app.services.ffmpeg_service import FFmpegCancelled, FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui.export_dialog import ExportDialog
from app.ui.preview_strip import MergedWaveStrip


@pytest.fixture
def project_with_sequences(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.4, name="Ouverture")
    sequence_service.add_sequence(project, ffmpeg_service, 0.4, 0.9, name="Question public 1")

    return project, ffmpeg_service


@pytest.fixture
def dialog(qtbot, project_with_sequences):
    project, ffmpeg_service = project_with_sequences
    widget = ExportDialog(project, ffmpeg_service)
    qtbot.addWidget(widget)
    return widget


# --- En-tête et fusion ----------------------------------------------------------


def test_the_header_counts_the_sequences_and_estimates_the_result(dialog):
    assert dialog._subtitle_label.text().startswith("2 séquences · durée estimée du résultat 00:00:0")


def test_a_crossfade_shortens_the_estimated_result(dialog):
    dialog._simple_merge_radio.setChecked(True)
    without = dialog._estimated_duration()

    dialog._crossfade_radio.setChecked(True)
    dialog._crossfade_slider.set_value(200)
    dialog._on_merge_mode_changed()

    assert dialog._estimated_duration() == pytest.approx(without - 0.2)


def test_the_crossfade_slider_only_applies_when_it_is_chosen(dialog):
    dialog._crossfade_radio.setChecked(True)
    dialog._crossfade_slider.set_value(300)
    dialog._on_merge_mode_changed()
    assert dialog._crossfade_seconds() == pytest.approx(0.3)

    dialog._simple_merge_radio.setChecked(True)

    assert dialog._crossfade_seconds() == 0.0
    assert not dialog._crossfade_slider.isEnabled()


def test_the_hint_spells_out_what_the_crossfade_costs(dialog):
    dialog._crossfade_radio.setChecked(True)
    dialog._crossfade_slider.set_value(250)
    dialog._on_merge_mode_changed()

    assert "1 jonctions" in dialog._merge_hint.text()
    assert "0,25 s" in dialog._merge_hint.text()


def test_simple_merge_says_so(dialog):
    dialog._simple_merge_radio.setChecked(True)

    assert "bout à bout" in dialog._merge_hint.text()


def test_the_chosen_crossfade_reaches_the_project(dialog, project_with_sequences):
    project, _service = project_with_sequences

    dialog._crossfade_radio.setChecked(True)
    dialog._crossfade_slider.set_value(400)
    dialog._on_merge_mode_changed()

    assert project.crossfade_duration == pytest.approx(0.4)


# --- Format de sortie -------------------------------------------------------------


def test_every_format_offers_its_own_qualities(dialog):
    for fmt in ("WAV", "MP3", "FLAC", "M4A", "OGG", "Opus"):
        dialog._format_segments.set_value(fmt)
        dialog._on_format_changed(fmt)
        assert dialog._quality_combo.count() > 0


def test_lossless_formats_ask_for_a_resolution_not_a_bitrate(dialog):
    dialog._on_format_changed("MP3")
    assert dialog._quality_label.text() == "Débit"

    dialog._on_format_changed("FLAC")
    assert dialog._quality_label.text() == "Résolution"


def test_the_sample_rate_can_be_left_as_the_source(dialog):
    dialog._sample_rate_combo.setCurrentIndex(0)
    assert dialog._selected_sample_rate() is None

    dialog._sample_rate_combo.setCurrentIndex(2)
    assert dialog._selected_sample_rate() == 48000


def test_a_chosen_sample_rate_reaches_the_exported_file(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences
    out_path = tmp_path / "resample.wav"

    export_project(project, ffmpeg_service, str(out_path), "WAV", "16", sample_rate=44100)

    import wave

    with wave.open(str(out_path), "rb") as result:
        assert result.getframerate() == 44100


# --- Ce qui est exporté ------------------------------------------------------------


def test_the_per_sequence_option_counts_the_files(dialog):
    assert dialog._separate_radio.text() == "Un fichier par séquence (2 fichiers)"


def test_choosing_per_sequence_proposes_a_folder(dialog, project_with_sequences):
    project, _service = project_with_sequences
    video = Path(project.source_video.path)

    dialog._separate_radio.setChecked(True)

    assert Path(dialog._path_edit.text()) == video.parent / f"{video.stem}_sequences"


def test_the_loudness_target_follows_the_checkbox(dialog):
    assert not dialog._lufs_spin.isEnabled()

    dialog._normalize_cb.setChecked(True)

    assert dialog._lufs_spin.isEnabled()


# --- Aperçu du résultat fusionné ------------------------------------------------------


def test_junctions_fall_between_the_sequences(dialog, project_with_sequences):
    project, _service = project_with_sequences
    dialog._simple_merge_radio.setChecked(True)
    total = dialog._estimated_duration()

    fractions = dialog._junction_fractions(total)

    first = sorted(project.sequences, key=lambda s: s.order)[0]
    assert fractions == [pytest.approx(first.duration / total, abs=0.01)]


def test_a_single_sequence_has_no_junction(dialog, project_with_sequences):
    project, _service = project_with_sequences
    project.sequences = project.sequences[:1]

    assert dialog._junction_fractions(10.0) == []


def test_building_the_preview_shows_the_wave_and_its_duration(qtbot, dialog):
    dialog._on_preview_clicked()
    qtbot.waitUntil(lambda: bool(dialog._preview_path), timeout=15000)

    assert dialog._preview_strip.has_wave
    assert dialog._preview_duration_label.text() not in ("—", "…")
    assert Path(dialog._preview_path).exists()


def test_changing_the_merge_settings_drops_the_preview(qtbot, dialog):
    dialog._on_preview_clicked()
    qtbot.waitUntil(lambda: bool(dialog._preview_path), timeout=15000)

    dialog._crossfade_radio.setChecked(True)

    assert dialog._preview_path == ""
    assert not dialog._preview_strip.has_wave


def test_the_merged_strip_marks_its_junctions(qtbot):
    from app.config.themes import get_theme

    strip = MergedWaveStrip()
    qtbot.addWidget(strip)
    strip.resize(400, 60)
    strip.set_theme(get_theme("Sombre"))
    peaks = np.stack([-np.ones(80) * 0.9, np.ones(80) * 0.9], axis=1)

    strip.set_wave(peaks, [0.5])
    image = strip.grab().toImage()
    ratio = image.devicePixelRatio()

    assert image.pixelColor(int(200 * ratio), int(30 * ratio)) != image.pixelColor(int(60 * ratio), int(30 * ratio))


def test_an_empty_merged_strip_does_not_crash(qtbot):
    strip = MergedWaveStrip()
    qtbot.addWidget(strip)

    assert not strip.has_wave
    strip.grab()


# --- Progression, étapes et annulation --------------------------------------------------


def test_the_export_announces_the_sequence_being_written(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences
    stages = []

    export_sequences_separately(
        project, ffmpeg_service, str(tmp_path / "seqs"), "WAV", "16", on_stage=stages.append
    )

    assert stages == ["séquence 1 sur 2 « Ouverture »", "séquence 2 sur 2 « Question public 1 »"]


def test_the_merged_export_announces_its_steps(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences
    stages = []

    export_project(
        project, ffmpeg_service, str(tmp_path / "out.wav"), "WAV", "16",
        normalize_lufs=-16.0, on_stage=stages.append,
    )

    assert stages == ["Fusion des séquences", "Normalisation du volume", "Encodage du fichier WAV"]


def test_a_cancelled_export_stops_and_is_not_an_error(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences

    with pytest.raises(FFmpegCancelled):
        export_sequences_separately(
            project, ffmpeg_service, str(tmp_path / "seqs"), "WAV", "16", should_cancel=lambda: True
        )

    assert not list((tmp_path / "seqs").glob("*.wav"))


def test_cancelling_never_starts_the_next_sequence(project_with_sequences, tmp_path):
    """L'arrêt est consulté pendant l'encodage comme entre deux séquences : demandé sur la
    première, il interrompt celle-ci et la suivante n'est jamais entamée. Le projet est intact."""
    project, ffmpeg_service = project_with_sequences
    stages: list[str] = []
    stop = {"asked": False}

    def announce(stage: str) -> None:
        stages.append(stage)
        stop["asked"] = True

    with pytest.raises(FFmpegCancelled):
        export_sequences_separately(
            project,
            ffmpeg_service,
            str(tmp_path / "seqs"),
            "WAV",
            "16",
            on_stage=announce,
            should_cancel=lambda: stop["asked"],
        )

    assert stages == ["séquence 1 sur 2 « Ouverture »"]
    assert len(project.sequences) == 2


def test_the_window_reports_a_cancelled_export_without_an_error_box(qtbot, dialog, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a))
    dialog._path_edit.setText(str(tmp_path / "out.wav"))

    dialog._on_export_clicked()
    dialog._on_cancel_clicked()
    qtbot.waitUntil(lambda: dialog._worker.isFinished(), timeout=15000)

    assert shown == []
    assert dialog._export_button.isEnabled()


def test_the_cancel_button_says_what_it_does(qtbot, dialog, tmp_path):
    assert dialog._cancel_button.text() == "Annuler"

    dialog._set_exporting(True)
    assert dialog._cancel_button.text() == "Interrompre l'export"
    assert dialog._progress_card.isVisibleTo(dialog)

    dialog._set_exporting(False)
    assert dialog._cancel_button.text() == "Annuler"
    assert not dialog._progress_card.isVisibleTo(dialog)


def test_the_remaining_time_is_estimated_from_the_elapsed_one(dialog):
    dialog._set_exporting(True)

    dialog._progress_bar.setValue(50)

    assert dialog._progress_percent.text() == "50 %"
    assert "Temps restant estimé" in dialog._progress_hint.text()
    assert "interrompu sans perdre le projet" in dialog._progress_hint.text()


def test_before_any_progress_only_the_cancellation_note_is_shown(dialog):
    dialog._set_exporting(True)

    assert dialog._progress_hint.text() == "L'export peut être interrompu sans perdre le projet."


def test_processed_sequences_are_what_gets_exported(project_with_sequences, tmp_path):
    """L'export prend la version traitée d'une séquence quand elle existe."""
    from app.services import audio_processor

    project, ffmpeg_service = project_with_sequences
    sequence = sorted(project.sequences, key=lambda s: s.order)[0]
    sequence.audio_settings = AudioSettings(gain=6.0)
    audio_processor.process_sequence(project, sequence, ffmpeg_service)

    written = export_sequences_separately(project, ffmpeg_service, str(tmp_path / "seqs"), "WAV", "16")

    assert ffmpeg_service.measure_peak_db(written[0]) > ffmpeg_service.measure_peak_db(sequence.audio_path)
