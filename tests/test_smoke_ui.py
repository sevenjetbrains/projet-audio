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
