"""Tests de la barre de contrôle du plein écran (progression, temps, lecture/pause) et de son intégration."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from app.ui.fullscreen_controls import FullscreenControls
from app.ui.transport_controls import TransportControls
from app.ui.video_player_panel import VideoPlayerPanel
from app.ui.video_preview import VideoPreview


@pytest.fixture
def controls(qtbot):
    widget = FullscreenControls()
    qtbot.addWidget(widget)
    widget.resize(800, 70)
    widget.show()
    return widget


class _Recorder:
    def __init__(self, controls):
        self.play, self.live, self.committed, self.skips = 0, [], [], []
        controls.play_toggled.connect(lambda: setattr(self, "play", self.play + 1))
        controls.seek_live.connect(self.live.append)
        controls.seek_committed.connect(self.committed.append)
        controls.skip_requested.connect(self.skips.append)


# --- affichage : temps et progression ---------------------------------------------------------------------


def test_shows_position_and_total_duration(controls):
    controls.set_duration(24.5)
    controls.set_position(7.16)

    assert controls._position_label.text() == "00:00:07,160"
    assert controls._duration_label.text() == "00:00:24,500"
    assert controls._slider.maximum() == 24500
    assert controls._slider.value() == 7160


def test_duration_follows_the_media_being_played(controls):
    controls.set_position(1.0, duration=10.0)
    assert controls._duration_label.text() == "00:00:10,000"

    controls.set_position(0.5, duration=3.5)  # une séquence remplace la source : le total change

    assert controls._duration_label.text() == "00:00:03,500"
    assert controls._slider.maximum() == 3500


def test_hours_are_shown_for_long_videos(controls):
    controls.set_position(3725.25, duration=7322.0)

    assert controls._position_label.text() == "01:02:05,250"
    assert controls._duration_label.text() == "02:02:02,000"


def test_position_updates_never_emit_seek_requests(controls):
    rec = _Recorder(controls)

    controls.set_duration(60.0)
    for seconds in (1.0, 2.0, 3.0):
        controls.set_position(seconds)

    assert rec.live == [] and rec.committed == []  # afficher la lecture n'est pas la déplacer


def test_playback_position_is_ignored_while_the_user_holds_the_slider(controls):
    controls.set_duration(60.0)
    controls.set_position(10.0)
    controls._slider.setSliderDown(True)
    controls._on_press()

    controls.set_position(11.0)  # la lecture avance pendant que l'utilisateur tient le curseur

    assert controls._slider.value() == 10_000  # le curseur n'est pas tiré en arrière
    assert controls._position_label.text() == "00:00:11,000"  # mais le temps réel reste affiché


# --- lecture / pause -------------------------------------------------------------------------------------


def test_play_button_emits_toggle(qtbot, controls):
    rec = _Recorder(controls)

    QTest.mouseClick(controls._play_button, Qt.MouseButton.LeftButton)

    assert rec.play == 1


def test_play_icon_and_tooltip_follow_playback_state(controls):
    controls.set_playing(False)
    paused_icon = controls._play_button.icon().pixmap(20, 20).toImage()
    assert controls._play_button.toolTip().startswith("Lecture")

    controls.set_playing(True)

    assert controls.is_playing
    assert controls._play_button.icon().pixmap(20, 20).toImage() != paused_icon
    assert controls._play_button.toolTip().startswith("Pause")


# --- déplacement -------------------------------------------------------------------------------------------


def test_dragging_emits_live_seeks_then_the_exact_position_on_release(controls):
    controls.set_duration(60.0)
    rec = _Recorder(controls)

    controls._on_press()
    controls._slider.setValue(10_000)
    controls._slider.setValue(25_000)
    assert rec.live == [10.0, 25.0]
    assert rec.committed == []

    controls._on_release()

    assert rec.committed == [25.0]
    assert not controls.is_dragging


def test_click_in_the_groove_jumps_to_the_clicked_position(qtbot, controls):
    controls.set_duration(100.0)
    rec = _Recorder(controls)
    slider = controls._slider
    x = slider.width() // 2

    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, pos=QPoint(x, slider.height() // 2))

    assert rec.committed, "un clic dans la rainure doit déplacer la lecture"
    assert rec.committed[-1] == pytest.approx(50.0, abs=3.0)  # au milieu de 100 s (marges du curseur comprises)


def test_slider_has_no_keyboard_focus_so_the_window_keeps_the_keys(controls):
    assert controls._slider.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert controls._play_button.focusPolicy() == Qt.FocusPolicy.NoFocus


# --- intégration à la fenêtre plein écran ----------------------------------------------------------------


@pytest.fixture
def preview(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    widget = VideoPreview(host)
    widget.host = host  # référence Python : sinon l'hôte est détruit à la sortie de la fixture
    widget.set_active(True)
    host.resize(500, 300)
    host.show()
    qtbot.waitExposed(host)
    return widget


@pytest.fixture(autouse=True)
def _mouse_is_elsewhere(preview, monkeypatch):
    """La barre reste affichée tant que la souris la survole : on ne veut pas dépendre du vrai curseur du testeur."""
    monkeypatch.setattr(preview.fullscreen_controls, "underMouse", lambda: False)


def test_controls_appear_over_the_video_at_the_bottom_of_the_fullscreen_window(qtbot, preview):
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    controls = preview.fullscreen_controls

    qtbot.waitUntil(lambda: window.width() > 600, timeout=2000)

    assert controls.parent() is window
    assert controls.isVisible()
    assert controls.width() == window.width()
    # Coordonnées converties dans le repère de la fenêtre plein écran : la barre est collée au bord bas.
    top_left = window.mapFromGlobal(controls.geometry().topLeft())
    assert top_left.x() == 0
    assert top_left.y() + controls.height() >= window.height() - 2
    assert top_left.y() > window.height() // 2


def test_controls_are_a_separate_window_so_the_native_video_surface_cannot_hide_them(preview):
    """Qt 6 dessine l'image dans une fenêtre native qui recouvre les widgets voisins : un widget enfant restait
    invisible derrière l'image. La barre doit donc être une fenêtre à part, posée par-dessus."""
    preview.toggle_fullscreen()
    controls = preview.fullscreen_controls

    assert controls.isWindow()
    flags = controls.windowFlags()
    assert flags & Qt.WindowType.Tool
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus  # les touches restent à la fenêtre plein écran
    assert controls.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_controls_follow_the_fullscreen_window_when_it_is_moved(qtbot, preview):
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    controls = preview.fullscreen_controls
    qtbot.waitUntil(lambda: window.width() > 600, timeout=2000)
    before = controls.geometry().topLeft()

    window.move(window.x() + 40, window.y() + 25)
    qtbot.waitUntil(lambda: controls.geometry().topLeft() != before, timeout=2000)

    assert controls.geometry().topLeft() - before == QPoint(40, 25)


def test_controls_survive_repeated_fullscreen_round_trips(preview):
    controls = preview.fullscreen_controls

    for _ in range(3):
        preview.toggle_fullscreen()
        assert controls.parent() is preview._fullscreen_window
        preview.toggle_fullscreen()
        assert controls.parent() is preview  # rendue à l'aperçu : pas détruite avec la fenêtre plein écran
        assert not controls.isVisible()

    controls.set_position(1.0, duration=2.0)  # toujours utilisable (objet Qt encore valide)
    assert controls._position_label.text() == "00:00:01,000"


def test_controls_hide_after_idle_while_playing(qtbot, preview):
    preview.fullscreen_controls.set_playing(True)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    controls = preview.fullscreen_controls
    window._idle_timer.setInterval(60)
    window._show_controls()
    assert controls.isVisible()

    qtbot.waitUntil(lambda: not controls.isVisible(), timeout=2000)

    assert window.cursor().shape() == Qt.CursorShape.BlankCursor  # le curseur disparaît avec la barre


def test_controls_stay_visible_while_paused(qtbot, preview):
    preview.fullscreen_controls.set_playing(False)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    window._idle_timer.setInterval(40)
    window._show_controls()

    qtbot.wait(250)

    assert preview.fullscreen_controls.isVisible()  # en pause on doit pouvoir lire le temps et rechercher


def test_controls_stay_visible_while_dragging(qtbot, preview):
    controls = preview.fullscreen_controls
    controls.set_playing(True)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    window._idle_timer.setInterval(40)
    controls._on_press()
    window._show_controls()

    qtbot.wait(250)

    assert controls.isVisible()
    controls._on_release()


def test_cursor_movement_wakes_the_controls_and_the_cursor(qtbot, preview, monkeypatch):
    controls = preview.fullscreen_controls
    controls.set_playing(True)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    window._idle_timer.setInterval(40)
    window._show_controls()
    qtbot.waitUntil(lambda: not controls.isVisible(), timeout=2000)

    class _MovedCursor:
        @staticmethod
        def pos():
            return QPoint(321, 654)

    monkeypatch.setattr("app.ui.video_preview.QCursor", _MovedCursor)
    window._poll_cursor()

    assert controls.isVisible()
    assert window.cursor().shape() != Qt.CursorShape.BlankCursor


def test_a_still_cursor_does_not_wake_the_controls(qtbot, preview, monkeypatch):
    controls = preview.fullscreen_controls
    controls.set_playing(True)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    window._idle_timer.setInterval(40)
    window._show_controls()
    qtbot.waitUntil(lambda: not controls.isVisible(), timeout=2000)

    class _SameCursor:
        @staticmethod
        def pos():
            return window._last_cursor

    monkeypatch.setattr("app.ui.video_preview.QCursor", _SameCursor)
    window._poll_cursor()

    assert not controls.isVisible()


# --- clavier ---------------------------------------------------------------------------------------------


def test_space_and_arrow_keys_drive_playback_in_fullscreen(qtbot, preview):
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    rec = _Recorder(preview.fullscreen_controls)

    QTest.keyClick(window, Qt.Key.Key_Space)
    QTest.keyClick(window, Qt.Key.Key_Right)
    QTest.keyClick(window, Qt.Key.Key_Left)

    assert rec.play == 1
    assert rec.skips == [5.0, -5.0]


def test_controls_stay_visible_while_the_mouse_is_over_them(qtbot, preview, monkeypatch):
    controls = preview.fullscreen_controls
    controls.set_playing(True)
    monkeypatch.setattr(controls, "underMouse", lambda: True)
    preview.toggle_fullscreen()
    window = preview._fullscreen_window
    window._idle_timer.setInterval(40)
    window._show_controls()

    qtbot.wait(250)

    assert controls.isVisible()


def test_a_key_received_by_the_bar_is_forwarded_to_the_fullscreen_window(qtbot, preview):
    preview.toggle_fullscreen()
    rec = _Recorder(preview.fullscreen_controls)

    QTest.keyClick(preview.fullscreen_controls, Qt.Key.Key_Space)

    assert rec.play == 1


def test_escape_still_leaves_fullscreen(preview):
    preview.toggle_fullscreen()

    QTest.keyClick(preview._fullscreen_window, Qt.Key.Key_Escape)

    assert not preview.is_fullscreen


# --- branchement sur le lecteur ---------------------------------------------------------------------------


@pytest.fixture
def panel(qtbot):
    try:
        transport = TransportControls()
    except Exception as exc:  # backend audio indisponible dans cet environnement
        pytest.skip(f"Backend audio indisponible : {exc}")
    qtbot.addWidget(transport)
    preview = VideoPreview()
    qtbot.addWidget(preview)
    widget = VideoPlayerPanel(transport, preview)
    qtbot.addWidget(widget)
    return widget, transport, preview.fullscreen_controls


def test_position_and_state_are_relayed_from_the_transport(panel):
    _panel, transport, controls = panel

    transport.position_changed.emit(12.5)
    transport.playing_changed.emit(True)

    assert controls._position_label.text() == "00:00:12,500"
    assert controls.is_playing


def test_controls_commands_reach_the_transport(panel, monkeypatch):
    _panel, transport, controls = panel
    calls = []
    monkeypatch.setattr(transport, "toggle_play_pause", lambda: calls.append("toggle"))
    monkeypatch.setattr(transport, "seek_throttled", lambda s: calls.append(("live", s)))
    monkeypatch.setattr(transport, "set_position_seconds", lambda s: calls.append(("exact", s)))
    monkeypatch.setattr(transport, "skip", lambda d: calls.append(("skip", d)))
    # Les connexions ont été faites avant les monkeypatch : on les refait sur les doubles.
    controls.play_toggled.disconnect()
    controls.seek_live.disconnect()
    controls.seek_committed.disconnect()
    controls.skip_requested.disconnect()
    _panel._wire_fullscreen_controls()

    controls.play_toggled.emit()
    controls.seek_live.emit(4.0)
    controls.seek_committed.emit(9.0)
    controls.skip_requested.emit(-5.0)

    assert calls == ["toggle", ("live", 4.0), ("exact", 9.0), ("skip", -5.0)]


# --- rendu : fond translucide, sans héritage du noir de la fenêtre ----------------------------------------------


def test_bar_background_is_translucent_black_not_opaque_and_not_transparent(qtbot, preview):
    preview.toggle_fullscreen()
    controls = preview.fullscreen_controls
    controls.resize(600, 68)

    pixel = controls.grab().toImage().pixelColor(4, 4)  # coin : pas de contrôle à cet endroit

    assert (pixel.red(), pixel.green(), pixel.blue()) == (0, 0, 0)
    # Ni transparent (texte blanc illisible sur une image claire), ni opaque (l'image disparaît derrière la barre).
    assert 100 < pixel.alpha() < 240


def test_black_of_the_fullscreen_window_is_not_inherited_by_the_bar_widgets(preview):
    preview.toggle_fullscreen()
    window = preview._fullscreen_window

    # Un style sans sélecteur (« background-color: black ») s'appliquait à tous les descendants, barre comprise :
    # le curseur de progression était entouré d'un rectangle noir opaque.
    assert window.styleSheet().lstrip().startswith("#")
    assert "fullscreenVideoWindow" in window.styleSheet()
    assert preview.fullscreen_controls._slider.styleSheet() == ""


def test_progress_slider_is_drawn_over_the_translucent_background(preview):
    preview.toggle_fullscreen()
    controls = preview.fullscreen_controls
    controls.resize(800, 68)
    controls.set_duration(100.0)
    controls.set_position(50.0)

    image = controls.grab().toImage()
    slider = controls._slider
    center = slider.mapTo(controls, slider.rect().center())
    ratio = image.devicePixelRatio()
    behind = image.pixelColor(int(center.x() * ratio), int((center.y() - 20) * ratio))  # au-dessus du curseur

    assert behind.alpha() < 240  # l'arrière-plan reste translucide autour du curseur (avant : bloc noir opaque)
