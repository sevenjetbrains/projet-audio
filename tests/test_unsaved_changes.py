"""Tests du suivi des modifications non sauvegardées (titre avec astérisque, confirmation à la fermeture)."""

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from app.config.settings import find_ffmpeg_binaries
from app.models.project import Project
from app.ui.main_window import MainWindow

_BUTTONS = QMessageBox.StandardButton


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    project = Project(name="mon_projet")
    monkeypatch.setattr(type(win._video_panel), "project", property(lambda self: project))
    win._update_window_title()
    return win


def _answer(monkeypatch, button):
    asked = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a), button)[1])
    return asked


def _close(window) -> bool:
    event = QCloseEvent()
    window.closeEvent(event)
    return event.isAccepted()


def test_title_without_project_is_app_name(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)

    assert win.windowTitle() == "AudioCut Studio"


def test_title_shows_project_name_and_asterisk_when_dirty(window):
    assert window.windowTitle() == "mon_projet — AudioCut Studio"

    window._mark_dirty()
    assert window.windowTitle() == "mon_projet * — AudioCut Studio"

    window._set_dirty(False)
    assert window.windowTitle() == "mon_projet — AudioCut Studio"


def test_sequence_and_crossfade_changes_mark_dirty(window):
    window._on_sequences_changed()
    assert window._dirty

    window._set_dirty(False)
    window._crossfade_spin.setValue(1.5)
    assert window._dirty


def test_processing_marks_dirty(window):
    window._audio_processing_panel.processed.emit()

    assert window._dirty


def test_audio_ready_resets_dirty_for_new_project(window, monkeypatch):
    window._mark_dirty()
    monkeypatch.setattr(window._waveform_widget, "load", lambda *a: None)
    monkeypatch.setattr(window._transport_controls, "set_source", lambda *a: None)

    window._on_audio_ready("x.wav", 5.0)

    assert not window._dirty


def test_close_when_clean_does_not_prompt(window, monkeypatch):
    asked = _answer(monkeypatch, _BUTTONS.Cancel)

    assert _close(window)
    assert asked == []


def test_close_dirty_cancel_keeps_window_open(window, monkeypatch):
    window._mark_dirty()
    asked = _answer(monkeypatch, _BUTTONS.Cancel)

    assert not _close(window)
    assert len(asked) == 1


def test_close_dirty_discard_closes_without_saving(window, monkeypatch):
    window._mark_dirty()
    _answer(monkeypatch, _BUTTONS.Discard)
    saved = []
    monkeypatch.setattr(window, "_save_project", lambda: saved.append(True) or True)

    assert _close(window)
    assert saved == []


def test_close_dirty_save_closes_only_if_save_succeeds(window, monkeypatch):
    window._mark_dirty()
    _answer(monkeypatch, _BUTTONS.Save)

    monkeypatch.setattr(window, "_save_project", lambda: False)  # l'utilisateur annule l'explorateur de fichiers
    assert not _close(window)

    monkeypatch.setattr(window, "_save_project", lambda: True)
    assert _close(window)


def test_save_project_writes_file_and_clears_dirty(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog

    written = []
    target = tmp_path / "demo"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    monkeypatch.setattr("app.ui.main_window.save_project", lambda project, path: written.append(path))
    monkeypatch.setattr("app.ui.main_window.add_recent_project", lambda path: None)
    window._mark_dirty()

    assert window._save_project()

    assert written == [str(target) + ".acsproject"]
    assert not window._dirty


def test_save_project_cancelled_keeps_dirty(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    window._mark_dirty()

    assert not window._save_project()
    assert window._dirty


def test_opening_another_project_asks_first_and_cancel_aborts(window, monkeypatch):
    window._mark_dirty()
    _answer(monkeypatch, _BUTTONS.Cancel)
    started = []
    monkeypatch.setattr("app.ui.main_window.FFmpegTaskWorker", lambda *a, **k: started.append(True))

    window._start_project_load("C:/projets/autre.acsproject")

    assert started == []


def test_autosave_recovery_does_not_prompt_and_stays_dirty(window, monkeypatch):
    window._mark_dirty()
    asked = _answer(monkeypatch, _BUTTONS.Cancel)
    monkeypatch.setattr(window._video_panel, "set_loaded_project", lambda project: None)

    class _Progress:
        def close(self):
            pass

    window._on_project_loaded(object(), _Progress(), None)  # path None = récupération d'une sauvegarde auto

    assert asked == []
    assert window._dirty


def test_loading_a_saved_project_is_clean(window, monkeypatch):
    window._mark_dirty()
    monkeypatch.setattr(window._video_panel, "set_loaded_project", lambda project: None)
    monkeypatch.setattr("app.ui.main_window.add_recent_project", lambda path: None)

    class _Progress:
        def close(self):
            pass

    window._on_project_loaded(object(), _Progress(), "C:/projets/demo.acsproject")

    assert not window._dirty
