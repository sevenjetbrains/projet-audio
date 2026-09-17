"""Smoke test : la fenêtre principale s'instancie sans planter."""

from app.ui.main_window import MainWindow


def test_main_window_instantiates(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "AudioCut Studio"
    assert window.centralWidget() is not None
