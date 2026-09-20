"""Tests du plein écran de l'aperçu vidéo (avant : l'image se détachait en petite fenêtre noire)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from app.ui.video_preview import VideoPreview, _FullscreenWindow


@pytest.fixture
def preview(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    widget = VideoPreview(host)
    widget.host = host  # référence Python : sans elle l'hôte (et l'aperçu qu'il contient) est détruit à la sortie de la fixture
    widget.set_active(True)
    host.resize(500, 300)
    host.show()
    qtbot.waitExposed(host)
    return widget


def _window(preview) -> _FullscreenWindow:
    return preview._fullscreen_window


def test_fullscreen_moves_the_video_into_a_real_fullscreen_window(qtbot, preview):
    preview.toggle_fullscreen()

    window = _window(preview)
    assert preview.is_fullscreen
    assert window is not None and window.isFullScreen()
    assert preview.video_widget.parent() is window
    # Le défaut d'origine : un widget devenu fenêtre à part, minuscule et sans état plein écran.
    assert not preview.video_widget.isWindow()
    qtbot.waitUntil(lambda: preview.video_widget.width() > 500, timeout=2000)


def test_fullscreen_covers_the_whole_screen(qtbot, preview):
    preview.toggle_fullscreen()
    window = _window(preview)

    qtbot.waitUntil(lambda: window.width() >= preview.screen().geometry().width() - 2, timeout=2000)

    assert window.height() >= preview.screen().geometry().height() - 2


def test_second_toggle_returns_the_video_to_its_place(qtbot, preview):
    preview.toggle_fullscreen()
    window = _window(preview)

    preview.toggle_fullscreen()

    assert not preview.is_fullscreen
    assert preview.video_widget.parent() is preview
    assert preview._stack.currentWidget() is preview.video_widget
    assert preview.video_widget.isVisible()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)


def test_toggle_twice_is_a_clean_round_trip_repeatedly(preview):
    for _ in range(4):
        preview.toggle_fullscreen()
        assert preview.is_fullscreen
        preview.toggle_fullscreen()
        assert not preview.is_fullscreen
        assert preview.video_widget.parent() is preview
        assert preview.is_active


def test_escape_leaves_fullscreen(qtbot, preview):
    preview.toggle_fullscreen()

    QTest.keyClick(_window(preview), Qt.Key.Key_Escape)

    assert not preview.is_fullscreen
    assert preview.video_widget.parent() is preview


def test_double_click_leaves_fullscreen(qtbot, preview):
    preview.toggle_fullscreen()

    QTest.mouseDClick(_window(preview), Qt.MouseButton.LeftButton)

    assert not preview.is_fullscreen


def test_closing_the_fullscreen_window_gives_the_video_back_instead_of_destroying_it(preview):
    preview.toggle_fullscreen()
    window = _window(preview)

    window.closeEvent(QCloseEvent())

    assert not preview.is_fullscreen
    assert preview.video_widget.parent() is preview
    assert preview.video_widget.isVisible()  # l'image n'est pas détruite avec la fenêtre


def test_nothing_to_show_means_no_fullscreen(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    empty = VideoPreview(host)  # message d'attente, aucune image
    empty.host = host
    host.show()

    empty.toggle_fullscreen()

    assert not empty.is_fullscreen
    assert empty._fullscreen_window is None


def test_stays_active_while_fullscreen(preview):
    preview.toggle_fullscreen()

    assert preview.is_active  # sinon « aucune image à enregistrer » alors qu'on la regarde


def test_switching_to_placeholder_leaves_fullscreen(preview):
    preview.toggle_fullscreen()

    preview.set_active(False)  # ex. repli sur l'audio seul si Qt ne sait pas décoder la vidéo

    assert not preview.is_fullscreen
    assert not preview.is_active
    assert preview.video_widget.parent() is preview


def test_reactivating_while_fullscreen_keeps_it(preview):
    preview.toggle_fullscreen()

    preview.set_active(True)

    assert preview.is_fullscreen
    assert preview.video_widget.parent() is _window(preview)


def test_closing_the_preview_while_fullscreen_closes_the_window_too(qtbot, preview):
    preview.toggle_fullscreen()
    window = _window(preview)

    preview.close()

    assert not preview.is_fullscreen
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)


def test_playback_state_survives_fullscreen(qtbot, preview):
    """La sortie vidéo reste le même widget : la lecture n'est ni interrompue ni rebranchée."""
    video_widget = preview.video_widget

    preview.toggle_fullscreen()
    assert preview.video_widget is video_widget
    preview.toggle_fullscreen()
    assert preview.video_widget is video_widget
