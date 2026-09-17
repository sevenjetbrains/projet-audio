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
