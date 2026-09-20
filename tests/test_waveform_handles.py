"""Tests des poignées de la sélection : les bornes se tirent directement sur la waveform."""

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.config.settings import find_ffmpeg_binaries
from app.ui.main_window import MainWindow
from app.ui.waveform_widget import _HANDLE_GRAB_PX, _MIN_SELECTION_SECONDS, WaveformWidget

# Largeur 400 px pour 10 s : 40 px par seconde.
_PX_PER_SECOND = 40


def _x(seconds: float) -> int:
    return int(seconds * _PX_PER_SECOND)


@pytest.fixture
def waveform(qtbot):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 200)
    widget._duration = 10.0
    widget._view_start, widget._view_end = 0.0, 10.0
    widget._peaks = np.zeros((400, 2))
    widget.set_selection(3.0, 7.0)  # bornes à x = 120 et x = 280
    widget.show()  # les mouvements de souris (survol) ne sont livrés qu'à un widget affiché
    qtbot.waitExposed(widget)
    return widget


def _press(widget, x):
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(x, 60))


def _move(widget, x, pressed=False):
    """Mouvement de souris envoyé directement au widget : QTest.mouseMove ne livre aucun événement ici."""
    button = Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton
    event = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(x, 60), QPointF(x, 60), Qt.MouseButton.NoButton, button, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(widget, event)


def _release(widget, x):
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(x, 60))


def _drag(widget, from_x, to_x, steps=4):
    _press(widget, from_x)
    for i in range(1, steps + 1):
        _move(widget, from_x + (to_x - from_x) * i // steps, pressed=True)
    _release(widget, to_x)


class _Signals:
    def __init__(self, widget):
        self.selection, self.seeks, self.clicks = [], [], []
        widget.selection_changed.connect(lambda s, e: self.selection.append((s, e)))
        widget.seek_requested.connect(self.seeks.append)
        widget.region_clicked.connect(self.clicks.append)


# --- détection des bornes -----------------------------------------------------------------------------------


def test_edge_at_finds_each_edge_within_the_grab_distance(waveform):
    assert waveform.edge_at(_x(3.0)) == "start"
    assert waveform.edge_at(_x(3.0) + _HANDLE_GRAB_PX) == "start"
    assert waveform.edge_at(_x(7.0) - _HANDLE_GRAB_PX) == "end"
    assert waveform.edge_at(_x(5.0)) is None  # au milieu de la sélection
    assert waveform.edge_at(_x(1.0)) is None  # hors de la sélection
    assert waveform.edge_at(_x(3.0) + _HANDLE_GRAB_PX + 3) is None  # trop loin


def test_no_edge_without_a_selection(waveform):
    waveform._selection = None

    assert waveform.edge_at(_x(3.0)) is None


def test_narrow_selection_picks_the_nearest_edge(waveform):
    waveform.set_selection(5.0, 5.1)  # bornes à 200 et 204 px : les deux à portée

    assert waveform.edge_at(199) == "start"
    assert waveform.edge_at(206) == "end"


def test_edge_positions_follow_the_zoom(waveform):
    waveform._view_start, waveform._view_end = 2.0, 8.0  # 66,7 px par seconde

    start_x = waveform._time_to_x(3.0)
    assert waveform.edge_at(start_x) == "start"
    assert waveform.edge_at(_x(3.0)) is None  # l'ancienne position (sans zoom) n'est plus la bonne


# --- curseur de survol --------------------------------------------------------------------------------------


def test_hovering_an_edge_shows_the_resize_cursor_and_leaving_restores_it(waveform):
    _move(waveform, _x(3.0) + 2)
    assert waveform.cursor().shape() == Qt.CursorShape.SplitHCursor

    _move(waveform, _x(5.0))
    assert waveform.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_leaving_the_widget_while_over_an_edge_restores_the_cursor(waveform):
    _move(waveform, _x(7.0))
    assert waveform.cursor().shape() == Qt.CursorShape.SplitHCursor

    QApplication.sendEvent(waveform, QEvent(QEvent.Type.Leave))

    assert waveform.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert waveform._hover_edge is None


def test_mouse_tracking_is_enabled_for_hover(waveform):
    assert waveform.hasMouseTracking()


# --- déplacer une borne -------------------------------------------------------------------------------------


def test_dragging_the_start_edge_moves_only_the_start(waveform):
    sig = _Signals(waveform)

    _drag(waveform, _x(3.0), _x(4.5))

    assert waveform._selection == pytest.approx((4.5, 7.0), abs=0.05)
    assert sig.selection[-1] == pytest.approx((4.5, 7.0), abs=0.05)


def test_dragging_the_end_edge_moves_only_the_end(waveform):
    _drag(waveform, _x(7.0), _x(8.5))

    assert waveform._selection == pytest.approx((3.0, 8.5), abs=0.05)


def test_the_selection_is_updated_live_while_dragging(waveform):
    sig = _Signals(waveform)

    _press(waveform, _x(3.0))
    _move(waveform, _x(3.5), pressed=True)
    first = list(sig.selection)
    _move(waveform, _x(4.0), pressed=True)
    _move(waveform, _x(4.5), pressed=True)
    still_pressed = list(sig.selection)  # avant tout relâchement
    _release(waveform, _x(4.5))

    assert first and still_pressed[-1][0] > first[-1][0]  # les champs et la boucle suivent avant le relâchement
    assert len(still_pressed) >= 3


def test_dragging_an_edge_neither_seeks_nor_creates_a_new_selection(waveform):
    sig = _Signals(waveform)

    _drag(waveform, _x(3.0), _x(4.0))

    assert sig.seeks == [] and sig.clicks == []  # ce n'est pas un clic dans la waveform
    end = waveform._selection[1]
    assert end == pytest.approx(7.0)  # l'autre borne n'a pas bougé : aucune nouvelle sélection créée


def test_start_cannot_cross_the_end(waveform):
    _drag(waveform, _x(3.0), _x(9.0))

    start, end = waveform._selection
    assert end == 7.0
    assert start == pytest.approx(7.0 - _MIN_SELECTION_SECONDS)


def test_end_cannot_cross_the_start(waveform):
    _drag(waveform, _x(7.0), _x(1.0))

    start, end = waveform._selection
    assert start == 3.0
    assert end == pytest.approx(3.0 + _MIN_SELECTION_SECONDS)


def test_edges_stay_within_the_audio(waveform):
    _drag(waveform, _x(3.0), -80)
    assert waveform._selection[0] == 0.0

    _drag(waveform, _x(7.0), 900)
    assert waveform._selection[1] == 10.0


def test_edge_can_be_grabbed_again_after_being_moved(waveform):
    _drag(waveform, _x(3.0), _x(5.0))

    assert waveform.edge_at(_x(5.0)) == "start"  # la poignée est maintenant à sa nouvelle place
    _drag(waveform, _x(5.0), _x(2.0))
    assert waveform._selection[0] == pytest.approx(2.0, abs=0.05)


def test_dragging_at_zoom_uses_the_visible_time_scale(waveform):
    waveform._view_start, waveform._view_end = 2.0, 8.0

    _drag(waveform, int(waveform._time_to_x(3.0)), int(waveform._time_to_x(4.0)))

    assert waveform._selection[0] == pytest.approx(4.0, abs=0.05)


def test_drag_state_is_cleared_after_release(waveform):
    _drag(waveform, _x(3.0), _x(4.0))

    assert waveform._edge_drag is None
    # La souris est encore sur la nouvelle borne : le curseur de redimensionnement reste, prêt pour un nouveau tirage.
    assert waveform.cursor().shape() == Qt.CursorShape.SplitHCursor


# --- comportement existant préservé ----------------------------------------------------------------------------


def test_pressing_away_from_the_edges_still_creates_a_new_selection(waveform):
    sig = _Signals(waveform)

    _drag(waveform, _x(8.0), _x(9.5))  # loin des bornes 3 s et 7 s

    assert waveform._selection == pytest.approx((8.0, 9.5), abs=0.05)
    assert sig.selection[-1] == pytest.approx((8.0, 9.5), abs=0.05)


def test_clicking_away_from_the_edges_still_seeks(waveform):
    sig = _Signals(waveform)

    _press(waveform, _x(5.0))
    _release(waveform, _x(5.0))

    assert sig.seeks and sig.seeks[-1] == pytest.approx(5.0, abs=0.05)


def test_pressing_inside_the_selection_away_from_edges_seeks(waveform):
    sig = _Signals(waveform)

    _press(waveform, _x(4.0))
    _release(waveform, _x(4.0))

    assert sig.seeks and waveform._selection == (3.0, 7.0)  # la sélection n'est pas modifiée


# --- dessin -----------------------------------------------------------------------------------------------------


def _pixel(widget, x, y):
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(x * ratio), int(y * ratio))


def test_handles_are_drawn_at_both_edges(waveform):
    edge = _pixel(waveform, _x(3.0), 20)
    beside = _pixel(waveform, _x(3.0) - 25, 20)  # hors de la sélection, loin de la poignée

    assert edge != beside
    assert _pixel(waveform, _x(7.0), 20) != _pixel(waveform, _x(7.0) + 25, 20)


def test_handles_use_the_theme_accent_color(waveform):
    from app.config.themes import THEMES

    waveform.set_theme(THEMES["Clair"])
    accent = QColor(THEMES["Clair"].color("accent"))

    pixel = _pixel(waveform, _x(3.0), 20)  # trait de la borne, hors de la poignée centrale

    # Le trait est translucide (il se mélange au fond) : on vérifie qu'il est de la teinte de l'accent (orange),
    # nettement différente du fond gris-bleu de la waveform.
    assert accent.red() - accent.blue() > 100
    assert pixel.red() - pixel.blue() > 100
    assert abs(pixel.red() - accent.red()) < 60


def test_hovered_handle_is_drawn_more_prominently(waveform):
    row = waveform.height() // 2 - 40  # hors de la poignée centrale : on ne regarde que le trait vertical
    idle = _pixel(waveform, _x(3.0) - 1, row)
    _move(waveform, _x(3.0))
    hovered = _pixel(waveform, _x(3.0) - 1, row)

    assert hovered != idle  # le trait s'élargit et devient opaque quand la souris est dessus


def test_no_handles_are_drawn_without_a_selection(waveform):
    waveform._selection = None

    a = _pixel(waveform, _x(3.0), 20)
    b = _pixel(waveform, _x(3.0) - 25, 20)

    assert a == b


# --- intégration à la fenêtre : la boucle suit la borne tirée -----------------------------------------------------


def test_dragging_an_edge_updates_the_listening_loop_and_the_fields(qtbot, monkeypatch):
    monkeypatch.setattr("app.ui.main_window.find_recoverable_autosaves", lambda: [])
    window = MainWindow(find_ffmpeg_binaries())
    qtbot.addWidget(window)
    updates = []
    monkeypatch.setattr(window._transport_controls, "update_range", lambda s, e: updates.append((s, e)))
    window._selection_card.set_range(30.0)

    window._on_selection_changed(4.0, 9.5)  # signal émis par la waveform quand on tire une borne

    assert updates[-1] == (4.0, 9.5)
    assert window._selection_start_spin.value() == 4.0
    assert window._selection_end_spin.value() == 9.5
    assert window._selection_card.listen_button.isEnabled()
