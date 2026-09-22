"""Tests du clic sur l'image vidéo : bascule lecture / pause, comme la plupart des lecteurs."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest

from app.ui.transport_controls import TransportControls
from app.ui.video_player_panel import VideoPlayerPanel
from app.ui.video_preview import VideoPreview

_LOADED = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)


@pytest.fixture
def transport(qtbot):
    try:
        widget = TransportControls()
    except Exception as exc:  # backend audio indisponible dans cet environnement
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def preview(qtbot):
    widget = VideoPreview()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def panel(qtbot, transport, preview):
    widget = VideoPlayerPanel(transport, preview)
    qtbot.addWidget(widget)
    return widget


def _click(widget) -> None:
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


# --- le widget vidéo lui-même --------------------------------------------------------------------


def test_video_widget_emits_clicked_on_left_click(qtbot, preview):
    clicks = []
    preview.video_widget.clicked.connect(lambda: clicks.append(True))

    _click(preview.video_widget)

    assert len(clicks) == 1


def test_video_widget_ignores_right_click(qtbot, preview):
    clicks = []
    preview.video_widget.clicked.connect(lambda: clicks.append(True))

    QTest.mouseClick(preview.video_widget, Qt.MouseButton.RightButton)

    assert clicks == []


def test_preview_forwards_the_click_from_its_video_widget(qtbot, preview):
    clicks = []
    preview.video_clicked.connect(lambda: clicks.append(True))

    _click(preview.video_widget)

    assert len(clicks) == 1


# --- branchement sur le lecteur (panel) -----------------------------------------------------------


def test_clicking_the_video_toggles_play_pause(qtbot, panel, transport, synthetic_wav_file):
    transport.set_source(synthetic_wav_file)
    qtbot.waitUntil(lambda: transport._player.mediaStatus() in _LOADED, timeout=5000)
    assert not transport.is_playing

    _click(panel._preview.video_widget)
    qtbot.waitUntil(lambda: transport.is_playing, timeout=3000)

    _click(panel._preview.video_widget)
    qtbot.waitUntil(lambda: not transport.is_playing, timeout=3000)


def test_clicking_without_a_loaded_source_does_nothing(qtbot, panel, transport):
    assert not transport._play_button.isEnabled()

    _click(panel._preview.video_widget)
    qtbot.wait(50)  # laisse une éventuelle bascule intempestive le temps de se produire

    assert not transport.is_playing  # toggle_play_pause est un no-op tant que rien n'est chargé


def test_clicking_still_works_once_the_video_is_reparented_into_fullscreen(qtbot, panel, transport, synthetic_wav_file):
    """La surface vidéo est déplacée dans une fenêtre plein écran séparée : le même objet, le même signal."""
    transport.set_source(synthetic_wav_file)
    qtbot.waitUntil(lambda: transport._player.mediaStatus() in _LOADED, timeout=5000)
    panel._preview.set_active(True)
    panel._preview.toggle_fullscreen()
    assert panel._preview.is_fullscreen

    _click(panel._preview.video_widget)
    qtbot.waitUntil(lambda: transport.is_playing, timeout=3000)

    panel._preview.toggle_fullscreen()
    assert not panel._preview.is_fullscreen
