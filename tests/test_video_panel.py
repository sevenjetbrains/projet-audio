"""Tests du panneau SOURCE : instanciation, version de FFmpeg, annulation d'un import."""

from PySide6.QtCore import QThread, Signal

from app.ui.video_panel import VideoPanel


def test_video_panel_instantiates(qtbot, ffmpeg_binaries):
    panel = VideoPanel(ffmpeg_binaries)
    qtbot.addWidget(panel)

    assert panel._import_button.text() == "Importer une vidéo"
    assert panel._progress_bar.isHidden()


def test_ffmpeg_version_is_readable(ffmpeg_binaries):
    from app.services.ffmpeg_service import FFmpegService

    version = FFmpegService(ffmpeg_binaries.ffmpeg_path).version()

    assert version and version[0].isdigit()


def test_unreadable_ffmpeg_reports_no_version(tmp_path):
    from app.services.ffmpeg_service import FFmpegService

    assert FFmpegService(str(tmp_path / "pas_de_ffmpeg.exe")).version() == ""


def test_extraction_stops_when_cancellation_is_requested(ffmpeg_binaries, sample_video, tmp_path):
    """L'annulation interrompt le processus et se distingue d'un échec."""
    import pytest

    from app.services.ffmpeg_service import FFmpegCancelled, FFmpegService

    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_path = tmp_path / "interrompu.wav"

    with pytest.raises(FFmpegCancelled):
        service.extract_audio(sample_video, str(out_path), 1.0, should_cancel=lambda: True)


class _NeverEndingWorker(QThread):
    """Doublure d'ExtractAudioWorker : la vidéo de test dure 1 s et s'extrait trop vite pour
    qu'on puisse l'annuler à coup sûr ; celle-ci tourne jusqu'à ce qu'on l'arrête."""

    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, *_args, parent=None) -> None:
        super().__init__(parent)
        self._stop = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            self.msleep(10)
        self.cancelled.emit()


def test_cancelling_an_import_leaves_no_half_built_project(qtbot, monkeypatch, ffmpeg_binaries, sample_video):
    from pathlib import Path

    monkeypatch.setattr("app.ui.video_panel.ExtractAudioWorker", _NeverEndingWorker)
    panel = VideoPanel(ffmpeg_binaries)
    qtbot.addWidget(panel)
    panel.import_video(sample_video)
    temp_dir = panel.project.temp_dir
    assert Path(temp_dir).exists()
    assert not panel._import_button.isEnabled()

    panel.cancel_extraction()
    qtbot.waitUntil(lambda: panel.project is None, timeout=5000)

    assert not Path(temp_dir).exists()
    assert panel._import_button.isEnabled()
    assert panel._extraction_card.isHidden()


def test_cancelling_outside_an_import_does_nothing(qtbot, ffmpeg_binaries):
    panel = VideoPanel(ffmpeg_binaries)
    qtbot.addWidget(panel)

    panel.cancel_extraction()  # ne doit pas lever
