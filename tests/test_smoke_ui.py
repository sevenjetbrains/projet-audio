"""Smoke test : la fenêtre principale s'instancie sans planter."""

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow


def test_main_window_instantiates(qtbot, monkeypatch):
    # Évite toute dépendance à l'état réel de temp/ (autosaves d'une session
    # précédente) : sinon MainWindow.__init__ planifie une QMessageBox.question
    # modale (récupération autosave) qui bloquerait ce test.
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    assert window.windowTitle() == "AudioCut Studio"
    assert window.centralWidget() is not None


def test_recent_projects_menu_lists_and_opens(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    project_file = tmp_path / "demo.acsproject"
    project_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.ui.main_window.load_recent_projects", lambda: [str(project_file)])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    opened = []
    monkeypatch.setattr(window, "_start_project_load", lambda path, remember=True: opened.append(path))

    window._populate_recent_menu()
    actions = window._recent_menu.actions()
    assert [a.text() for a in actions] == ["demo.acsproject"]

    actions[0].trigger()
    assert opened == [str(project_file)]


def test_recent_projects_menu_empty(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    monkeypatch.setattr("app.ui.main_window.load_recent_projects", lambda: [])

    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)

    window._populate_recent_menu()
    assert [(a.text(), a.isEnabled()) for a in window._recent_menu.actions()] == [("(aucun)", False)]


def _window_with_duration(qtbot, monkeypatch, duration=10.0):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    for spin in (window._selection_start_spin, window._selection_end_spin):
        spin.setRange(0.0, duration)
    return window


def test_mark_in_out_shortcuts_set_selection_from_playhead(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 2.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))

    window._mark_selection_start()
    position["value"] = 6.5
    window._mark_selection_end()

    assert window._selection_start_spin.value() == 2.0
    assert window._selection_end_spin.value() == 6.5


def test_mark_in_after_out_pushes_end_forward(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 3.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))
    window._mark_selection_end()

    position["value"] = 8.0
    window._mark_selection_start()

    assert window._selection_start_spin.value() == 8.0
    assert window._selection_end_spin.value() == 8.0


def test_mark_out_before_in_pulls_start_back(qtbot, monkeypatch):
    window = _window_with_duration(qtbot, monkeypatch)
    position = {"value": 5.0}
    monkeypatch.setattr(type(window._transport_controls), "position_seconds", property(lambda self: position["value"]))
    window._mark_selection_start()

    position["value"] = 1.0
    window._mark_selection_end()

    assert window._selection_start_spin.value() == 1.0
    assert window._selection_end_spin.value() == 1.0


def test_enter_shortcut_creates_sequence_from_selection(qtbot, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence, QShortcut

    window = _window_with_duration(qtbot, monkeypatch)
    calls = []
    monkeypatch.setattr(window._sequence_list, "add_sequence_from_selection", lambda s, e: calls.append((s, e)))
    window._selection_start_spin.setValue(1.0)
    window._selection_end_spin.setValue(4.0)

    enter_shortcuts = [
        sc for sc in window.findChildren(QShortcut)
        if sc.key() in (QKeySequence(Qt.Key.Key_Return), QKeySequence(Qt.Key.Key_Enter))
    ]
    assert len(enter_shortcuts) == 2

    window._on_create_sequence_clicked()
    assert calls == [(1.0, 4.0)]
