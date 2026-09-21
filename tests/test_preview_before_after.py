"""Tests de l'aperçu « écouter avant / après » : extrait préparé, bande, enchaînement des deux versions."""

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtMultimedia import QMediaPlayer

from app.models.audio_settings import AudioSettings
from app.services import audio_processor, sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.preview_strip import BeforeAfterStrip


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


# --- Préparation de l'extrait -------------------------------------------------


def test_build_preview_writes_a_raw_and_a_processed_extract(project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    before, after = audio_processor.build_preview(
        project, sequence, ffmpeg_service, AudioSettings(gain=6.0), seconds=15.0
    )

    assert before != after
    assert Path(before).exists() and Path(after).exists()
    assert ffmpeg_service.measure_peak_db(after) > ffmpeg_service.measure_peak_db(before)


def test_build_preview_is_capped_by_the_sequence_duration(project_with_sequence):
    from app.services.ffmpeg_service import wav_duration

    project, sequence, ffmpeg_service = project_with_sequence

    before, _after = audio_processor.build_preview(
        project, sequence, ffmpeg_service, AudioSettings(gain=1.0), seconds=15.0
    )

    assert wav_duration(before) == pytest.approx(sequence.duration, abs=0.05)


def test_without_any_processing_both_sides_are_the_same_file(project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    before, after = audio_processor.build_preview(
        project, sequence, ffmpeg_service, AudioSettings(), seconds=15.0
    )

    assert before == after


def test_rebuilding_the_preview_reuses_the_same_files(project_with_sequence):
    """Un aperçu est jetable : pas la peine d'accumuler un fichier par réglage essayé."""
    project, sequence, ffmpeg_service = project_with_sequence

    first = audio_processor.build_preview(project, sequence, ffmpeg_service, AudioSettings(gain=2.0), 15.0)
    second = audio_processor.build_preview(project, sequence, ffmpeg_service, AudioSettings(gain=8.0), 15.0)

    assert first == second


# --- Bande avant / après --------------------------------------------------------


def _strip(qtbot) -> BeforeAfterStrip:
    strip = BeforeAfterStrip()
    qtbot.addWidget(strip)
    strip.resize(400, 60)
    return strip


def test_an_empty_strip_paints_nothing_and_does_not_crash(qtbot):
    strip = _strip(qtbot)

    assert not strip.has_peaks
    strip.grab()


def test_the_two_halves_use_different_colours(qtbot):
    from app.config.themes import get_theme

    strip = _strip(qtbot)
    strip.set_theme(get_theme("Sombre"))
    peaks = np.stack([-np.ones(60) * 0.9, np.ones(60) * 0.9], axis=1)

    strip.set_peaks(peaks, peaks)
    image = strip.grab().toImage()
    ratio = image.devicePixelRatio()

    left = image.pixelColor(int(100 * ratio), int(30 * ratio))
    right = image.pixelColor(int(300 * ratio), int(30 * ratio))
    assert left != right


def test_the_playhead_appears_only_while_playing(qtbot):
    from app.config.themes import get_theme

    strip = _strip(qtbot)
    strip.set_theme(get_theme("Sombre"))
    peaks = np.zeros((60, 2))
    strip.set_peaks(peaks, peaks)
    idle = strip.grab().toImage()

    strip.set_progress(0.5)
    assert strip.grab().toImage() != idle

    strip.set_progress(None)
    assert strip.grab().toImage() == idle


def test_clearing_forgets_both_the_peaks_and_the_playhead(qtbot):
    strip = _strip(qtbot)
    peaks = np.zeros((60, 2))
    strip.set_peaks(peaks, peaks)
    strip.set_progress(0.3)

    strip.clear()

    assert not strip.has_peaks
    assert strip._progress is None


# --- Enchaînement dans le panneau --------------------------------------------------


@pytest.fixture
def panel(qtbot, project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    widget = AudioProcessingPanel(ffmpeg_service)
    qtbot.addWidget(widget)
    widget.set_project(project)
    widget.set_sequence(sequence)
    return widget


def test_the_subtitle_names_the_sequence_and_the_extract_length(panel, project_with_sequence):
    """Séquence plus courte que la fenêtre d'aperçu : on l'écoute en entier."""
    _project, sequence, _service = project_with_sequence

    assert panel._preview_subtitle.text() == f"sur « {sequence.name} », en entier"


def test_a_long_sequence_announces_the_first_seconds(panel):
    from app.models.sequence import Sequence

    panel.set_sequence(Sequence(id="x", name="Q2", source_start=0.0, source_end=90.0, order=0))

    assert panel._preview_subtitle.text() == "sur « Q2 », 15 premières secondes"


def test_clicking_prepares_the_extract_and_shows_both_waveforms(qtbot, panel):
    panel._gain_slider.set_value(4.0)

    panel._on_preview_clicked()
    qtbot.waitUntil(lambda: panel._preview_paths is not None, timeout=15000)

    assert panel._preview_strip.has_peaks
    assert panel._preview_button.isEnabled()
    before, after = panel._preview_paths
    assert Path(before).exists() and Path(after).exists()


def test_the_raw_extract_is_played_first_then_the_processed_one(qtbot, panel, monkeypatch):
    played = []
    monkeypatch.setattr(panel._preview_player, "setSource", lambda url: played.append(url.toLocalFile()))
    monkeypatch.setattr(panel._preview_player, "play", lambda: None)
    panel._preview_paths = ("C:/x/avant.wav", "C:/x/apres.wav")

    panel._play_preview_phase(0)
    assert panel._preview_phase == 0

    panel._on_preview_status(QMediaPlayer.MediaStatus.EndOfMedia)

    assert panel._preview_phase == 1
    assert played == ["C:/x/avant.wav", "C:/x/apres.wav"]


def test_the_end_of_the_processed_extract_stops_the_preview(qtbot, panel, monkeypatch):
    stopped = []
    monkeypatch.setattr(panel._preview_player, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(panel._preview_player, "setSource", lambda _url: None)
    monkeypatch.setattr(panel._preview_player, "play", lambda: None)
    panel._preview_paths = ("a.wav", "b.wav")
    panel._play_preview_phase(1)

    panel._on_preview_status(QMediaPlayer.MediaStatus.EndOfMedia)

    assert stopped == [True]
    assert panel._preview_strip._progress is None


def test_the_progress_spans_both_halves(qtbot, panel, monkeypatch):
    monkeypatch.setattr(panel._preview_player, "duration", lambda: 1000)

    panel._preview_phase = 0
    panel._on_preview_position(500)
    assert panel._preview_strip._progress == pytest.approx(0.25)

    panel._preview_phase = 1
    panel._on_preview_position(500)
    assert panel._preview_strip._progress == pytest.approx(0.75)


def test_changing_sequence_drops_the_previous_preview(qtbot, panel, project_with_sequence):
    project, _sequence, ffmpeg_service = project_with_sequence
    other = sequence_service.add_sequence(project, ffmpeg_service, 0.1, 0.5, name="Autre")
    panel._on_preview_clicked()
    qtbot.waitUntil(lambda: panel._preview_paths is not None, timeout=15000)

    panel.set_sequence(other)

    assert panel._preview_paths is None
    assert not panel._preview_strip.has_peaks
    assert "Autre" in panel._preview_subtitle.text()
