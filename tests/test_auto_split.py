"""Tests du découpage automatique en séquences selon les silences."""

import wave
from pathlib import Path

import numpy as np
import pytest

from app.models.media import MediaInfo
from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegService
from app.services.project_service import create_project_for_video
from app.services.sequence_service import AutoSplitParams, create_sequences_from_silences, detect_speech_ranges
from app.ui.auto_split_dialog import AutoSplitDialog
from app.ui.sequence_list import SequenceListWidget

_RATE = 8000


def _tone(seconds: float) -> np.ndarray:
    t = np.arange(int(_RATE * seconds)) / _RATE
    return (0.5 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(_RATE * seconds), dtype=np.int16)


@pytest.fixture
def project_with_speech_pattern(ffmpeg_binaries):
    """Audio de 7 s : tonalité 2 s, silence 1 s, tonalité 0,3 s, silence 1 s, tonalité 2,7 s."""
    samples = np.concatenate([_tone(2.0), _silence(1.0), _tone(0.3), _silence(1.0), _tone(2.7)])
    duration = len(samples) / _RATE

    media_info = MediaInfo(
        path="demo.mp4", duration=duration, container_format="mp4", video_codec="h264",
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
    return project, FFmpegService(ffmpeg_binaries.ffmpeg_path)


def test_detect_speech_ranges_finds_segments_between_silences(project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern
    params = AutoSplitParams(min_silence=0.5, keep_padding=0.0, min_segment=0.0)

    ranges = detect_speech_ranges(project, ffmpeg_service, params)

    assert len(ranges) == 3
    assert ranges[0][0] == pytest.approx(0.0, abs=0.1) and ranges[0][1] == pytest.approx(2.0, abs=0.15)
    assert ranges[1][0] == pytest.approx(3.0, abs=0.15) and ranges[1][1] == pytest.approx(3.3, abs=0.15)
    assert ranges[2][0] == pytest.approx(4.3, abs=0.15) and ranges[2][1] == pytest.approx(7.0, abs=0.1)


def test_min_segment_drops_short_passages(project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern
    params = AutoSplitParams(min_silence=0.5, keep_padding=0.0, min_segment=1.0)

    assert len(detect_speech_ranges(project, ffmpeg_service, params)) == 2


def test_create_sequences_from_silences_cuts_and_names_sequences(project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 1.0)

    sequences = create_sequences_from_silences(
        project, ffmpeg_service, AutoSplitParams(keep_padding=0.0, min_segment=1.0)
    )

    assert [seq.name for seq in sequences] == ["Séquence 2", "Séquence 3"]
    assert all(Path(seq.audio_path).exists() for seq in sequences)
    # Non rattachées au projet tant que l'UI ne les insère pas (undo/redo).
    assert len(project.sequences) == 1


def test_detect_speech_ranges_requires_source_audio(ffmpeg_binaries):
    project = create_project_for_video(
        MediaInfo(
            path="x.mp4", duration=1.0, container_format="mp4", video_codec="h264",
            audio_codec="aac", sample_rate=8000, channels=1, resolution=None, bitrate=None, size_bytes=1,
        )
    )
    with pytest.raises(ValueError):
        detect_speech_ranges(project, FFmpegService(ffmpeg_binaries.ffmpeg_path), AutoSplitParams())


def test_sequence_list_add_sequences_is_one_undoable_action(qtbot, project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern
    widget = SequenceListWidget(ffmpeg_service)
    qtbot.addWidget(widget)
    widget.set_project(project)
    sequences = create_sequences_from_silences(project, ffmpeg_service, AutoSplitParams(min_segment=1.0))

    widget.add_sequences(sequences)
    assert len(project.sequences) == 2
    assert [seq.order for seq in project.sequences] == [0, 1]

    widget.undo_stack.undo()
    assert project.sequences == []

    widget.undo_stack.redo()
    assert len(project.sequences) == 2


def test_dialog_returns_defaults_and_edited_values(qtbot):
    dialog = AutoSplitDialog()
    qtbot.addWidget(dialog)
    assert dialog.params() == AutoSplitParams()

    dialog._threshold_spin.setValue(-50.0)
    dialog._min_segment_spin.setValue(2.0)

    assert dialog.params() == AutoSplitParams(threshold_db=-50.0, min_segment=2.0)


# --- aperçu des passages détectés ----------------------------------------------------------------------------


def test_create_sequences_from_ranges_cuts_only_the_given_ranges(project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern
    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 1.0)

    sequences = sequence_service.create_sequences_from_ranges(project, ffmpeg_service, [(0.5, 1.5), (4.5, 6.5)])

    assert [seq.name for seq in sequences] == ["Séquence 2", "Séquence 3"]
    assert [(seq.source_start, seq.source_end) for seq in sequences] == [(0.5, 1.5), (4.5, 6.5)]
    assert all(Path(seq.audio_path).exists() for seq in sequences)
    assert len(project.sequences) == 1  # non rattachées : c'est l'interface qui les insère (annulable)


def test_create_sequences_from_ranges_with_no_range_returns_nothing(project_with_speech_pattern):
    project, ffmpeg_service = project_with_speech_pattern

    assert sequence_service.create_sequences_from_ranges(project, ffmpeg_service, []) == []


def test_preview_dialog_lists_every_range_checked_by_default(qtbot):
    from app.ui.split_preview_dialog import SplitPreviewDialog

    ranges = [(0.0, 2.0), (3.0, 3.5), (4.0, 7.0)]
    dialog = SplitPreviewDialog(ranges)
    qtbot.addWidget(dialog)

    assert dialog._table.rowCount() == 3
    assert dialog.selected_ranges() == ranges
    assert dialog._table.item(1, 4).text() == "00:00:00.500"  # durée du 2e passage
    assert "3 sur 3" in dialog._summary.text()


def test_preview_dialog_unchecking_removes_range_and_updates_summary(qtbot):
    from PySide6.QtCore import Qt

    from app.ui.split_preview_dialog import SplitPreviewDialog

    ranges = [(0.0, 2.0), (3.0, 3.5), (4.0, 7.0)]
    dialog = SplitPreviewDialog(ranges)
    qtbot.addWidget(dialog)

    dialog._table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)

    assert dialog.selected_ranges() == [ranges[0], ranges[2]]
    assert "2 sur 3" in dialog._summary.text()
    assert "00:00:05.000" in dialog._summary.text()  # 2 s + 3 s


def test_preview_dialog_select_none_disables_confirmation(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialogButtonBox

    from app.ui.split_preview_dialog import SplitPreviewDialog

    dialog = SplitPreviewDialog([(0.0, 2.0), (3.0, 4.0)])
    qtbot.addWidget(dialog)
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()

    dialog._set_all(Qt.CheckState.Unchecked)

    assert dialog.selected_ranges() == []
    assert not ok.isEnabled()


def _window(qtbot, monkeypatch):
    from app.config.settings import find_ffmpeg_binaries
    from app.ui.main_window import MainWindow

    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    return window


class _Progress:
    def close(self):
        pass


def test_window_creates_only_the_ranges_chosen_in_the_preview(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    window = _window(qtbot, monkeypatch)
    ranges = [(0.0, 2.0), (3.0, 3.5), (4.0, 7.0)]

    class FakePreview:
        DialogCode = QDialog.DialogCode

        def __init__(self, given, parent=None):
            assert given == ranges
        def exec(self):
            return QDialog.DialogCode.Accepted
        def selected_ranges(self):
            return [ranges[0], ranges[2]]

    created = []
    monkeypatch.setattr("app.ui.main_window.SplitPreviewDialog", FakePreview)
    monkeypatch.setattr(
        "app.ui.main_window.create_sequences_from_ranges", lambda project, service, chosen: created.append(chosen) or []
    )
    monkeypatch.setattr(type(window._video_panel), "project", property(lambda self: object()))

    window._on_split_ranges_detected(ranges, _Progress())
    qtbot.waitUntil(lambda: window._split_worker.isFinished(), timeout=3000)

    assert created == [[ranges[0], ranges[2]]]
    # La carte annonce les 3 passages détectés (avant le choix), pas seulement les 2 retenus.
    assert window._silence_card._detected_label.text() == "3 séquences détectées"


def test_window_cancelled_preview_creates_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    window = _window(qtbot, monkeypatch)

    class FakePreview:
        DialogCode = QDialog.DialogCode

        def __init__(self, given, parent=None):
            pass
        def exec(self):
            return QDialog.DialogCode.Rejected

    called = []
    monkeypatch.setattr("app.ui.main_window.SplitPreviewDialog", FakePreview)
    monkeypatch.setattr("app.ui.main_window.create_sequences_from_ranges", lambda *a: called.append(a) or [])

    window._on_split_ranges_detected([(0.0, 2.0)], _Progress())

    assert called == []


def test_window_reports_when_nothing_is_detected(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot, monkeypatch)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))

    window._on_split_ranges_detected([], _Progress())

    assert shown == ["Aucun passage détecté avec ces réglages."]
