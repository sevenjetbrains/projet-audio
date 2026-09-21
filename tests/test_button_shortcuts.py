"""Tests des raccourcis clavier : présence, unicité dans la fenêtre, infobulles, et action déclenchée."""

from collections import Counter

import pytest
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractButton

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow
from app.ui.shortcuts import set_button_shortcut


@pytest.fixture
def window(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    win = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(win)
    return win


def _all_shortcuts(window) -> list[str]:
    keys = [b.shortcut().toString() for b in window.findChildren(QAbstractButton) if not b.shortcut().isEmpty()]
    keys += [a.shortcut().toString() for a in window.findChildren(QAction) if not a.shortcut().isEmpty()]
    keys += [s.key().toString() for s in window.findChildren(QShortcut)]
    return keys


def test_no_shortcut_is_bound_twice(window):
    duplicates = [key for key, count in Counter(_all_shortcuts(window)).items() if count > 1]

    assert duplicates == []


def test_expected_button_shortcuts_are_registered(window):
    expected = {
        window._sequence_list._delete_button: "Delete",
        window._sequence_list._duplicate_button: "Ctrl+D",
        window._sequence_list._rename_button: "F2",
        window._sequence_list._play_button: "Ctrl+L",
        window._audio_processing_panel._apply_button: "Ctrl+Return",
        window._audio_processing_panel._reset_button: "Ctrl+R",
        window._merge_preview_button: "Ctrl+M",
        window._transport_controls._back_button: "Alt+Left",
        window._transport_controls._forward_button: "Alt+Right",
        window._transport_controls._stop_button: "Ctrl+Space",
    }
    for button, key in expected.items():
        assert button.shortcut() == QKeySequence(key), button.text()


def test_tooltips_mention_the_shortcut(window):
    tooltip = window._sequence_list._delete_button.toolTip()

    assert tooltip.startswith("Supprimer (")
    assert QKeySequence("Delete").toString(QKeySequence.SequenceFormat.NativeText) in tooltip
    assert "Ctrl+M" in window._merge_preview_button.toolTip()
    assert "Entrée" in window._create_sequence_button.toolTip()


def test_set_button_shortcut_helper(qtbot):
    from PySide6.QtWidgets import QPushButton

    button = QPushButton("Action")
    qtbot.addWidget(button)

    set_button_shortcut(button, "Ctrl+K")
    assert button.shortcut() == QKeySequence("Ctrl+K")
    assert button.toolTip() == "Action (Ctrl+K)"

    set_button_shortcut(button, "Ctrl+K", "Faire l'action")
    assert button.toolTip() == "Faire l'action (Ctrl+K)"


def test_sequence_buttons_call_their_handlers(window, monkeypatch):
    calls = []
    sequence_list = window._sequence_list
    for name in ("delete", "duplicate", "rename", "play"):
        monkeypatch.setattr(sequence_list, f"_on_{name}_clicked", lambda n=name: calls.append(n))

    for button in (
        sequence_list._delete_button,
        sequence_list._duplicate_button,
        sequence_list._rename_button,
        sequence_list._play_button,
    ):
        button.click()

    assert calls == ["delete", "duplicate", "rename", "play"]


def test_delete_button_removes_selected_sequence(window):
    from app.models.project import Project
    from app.models.sequence import Sequence
    from app.services import sequence_service

    project = Project(name="demo")
    sequence = Sequence(id="a", name="A", source_start=0.0, source_end=1.0, order=0)
    sequence_service.insert_sequence(project, sequence)
    window._sequence_list.set_project(project)
    window._sequence_list._list_widget.setCurrentRow(0)
    window._sequence_list._list_widget.item(0).setSelected(True)

    window._sequence_list._delete_button.click()

    assert project.sequences == []


def test_every_documented_shortcut_is_really_bound(window):
    from app.ui.shortcuts import SHORTCUTS_HELP

    bound = set(_all_shortcuts(window))
    bound.add("Space")  # Qt.Key_Space : le QShortcut de la barre de lecture est exposé sous ce nom
    documented = [key for entries in SHORTCUTS_HELP.values() for key, _ in entries]

    missing = [key for key in documented if QKeySequence(key).toString() not in bound]
    assert missing == []


def test_help_menu_shows_all_shortcuts(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a))

    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "Aide")
    action = help_menu.actions()[0]
    assert action.shortcut() == QKeySequence("F1")
    action.trigger()

    title, html = shown[0][1], shown[0][2]
    assert title == "Raccourcis clavier"
    assert "Supprimer" in html and "Fusionner et prévisualiser" in html and "Appliquer le traitement" in html
