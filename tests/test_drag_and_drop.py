"""Tests du glisser-déposer de fichiers sur la fenêtre principale."""

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    return win


def _mime(*paths: str) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    return mime


def _drop(window, *paths: str) -> QDropEvent:
    mime = _mime(*paths)  # l'événement Qt ne prend pas possession du QMimeData : il doit rester en vie
    event = QDropEvent(
        QPointF(5, 5), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier
    )
    window.dropEvent(event)
    return event


def test_window_accepts_drops(window):
    assert window.acceptDrops()


def test_drag_enter_accepts_video_and_project_only(window):
    def entered(path):
        mime = _mime(path)  # doit rester en vie tant que l'événement existe
        event = QDragEnterEvent(
            QPointF(5, 5).toPoint(), Qt.DropAction.CopyAction, mime,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        window.dragEnterEvent(event)
        return event.isAccepted()

    assert entered("C:/videos/clip.MP4")
    assert entered("C:/projets/demo.acsproject")
    assert not entered("C:/docs/notes.txt")


def test_drop_video_starts_import(window, monkeypatch):
    imported = []
    monkeypatch.setattr(window._video_panel, "import_video", imported.append)

    event = _drop(window, "C:/docs/notes.txt", "C:/videos/clip.mkv")

    assert event.isAccepted()
    assert imported == ["C:/videos/clip.mkv"]


def test_drop_project_loads_it(window, monkeypatch):
    loaded = []
    monkeypatch.setattr(window, "_start_project_load", loaded.append)

    _drop(window, "C:/projets/demo.acsproject")

    assert loaded == ["C:/projets/demo.acsproject"]


def test_drop_unsupported_file_is_ignored(window, monkeypatch):
    imported = []
    monkeypatch.setattr(window._video_panel, "import_video", imported.append)

    event = _drop(window, "C:/docs/notes.txt")

    assert not event.isAccepted()
    assert imported == []


def test_import_video_is_refused_while_extracting(window, monkeypatch):
    probed = []
    monkeypatch.setattr(window._video_panel._ffprobe_service, "probe", lambda p: probed.append(p))
    window._video_panel._import_button.setEnabled(False)  # extraction en cours

    window._video_panel.import_video("C:/videos/clip.mp4")

    assert window._video_panel.is_busy
    assert probed == []


def test_import_video_runs_full_import(qtbot, window, sample_video):
    with qtbot.waitSignal(window._video_panel.audio_ready, timeout=15000):
        window._video_panel.import_video(sample_video)

    assert window._video_panel.project is not None
    assert not window._video_panel.is_busy
