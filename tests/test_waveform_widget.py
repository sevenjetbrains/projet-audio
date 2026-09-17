"""Tests de WaveformWidget : sélection à la souris, seek au clic, zoom."""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent

from app.ui.waveform_widget import WaveformWidget


def _load_and_wait(qtbot, widget: WaveformWidget, wav_path: str, duration: float) -> None:
    widget.load(wav_path, duration)
    qtbot.waitUntil(lambda: widget._peaks is not None, timeout=5000)


def test_drag_selection_emits_signal(qtbot, synthetic_wav_file):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 150)
    _load_and_wait(qtbot, widget, synthetic_wav_file, 2.0)

    with qtbot.waitSignal(widget.selection_changed, timeout=2000) as blocker:
        qtbot.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(50, 75))
        qtbot.mouseMove(widget, pos=QPoint(150, 75))
        qtbot.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(150, 75))

    start, end = blocker.args
    assert 0.0 <= start < end <= 2.0


def test_simple_click_emits_seek(qtbot, synthetic_wav_file):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 150)
    _load_and_wait(qtbot, widget, synthetic_wav_file, 2.0)

    with qtbot.waitSignal(widget.seek_requested, timeout=2000) as blocker:
        qtbot.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 75))
        qtbot.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 75))

    assert 0.0 <= blocker.args[0] <= 2.0


def test_zoom_reduces_visible_span(qtbot, synthetic_wav_file):
    widget = WaveformWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 150)
    _load_and_wait(qtbot, widget, synthetic_wav_file, 2.0)

    initial_span = widget._view_end - widget._view_start

    event = QWheelEvent(
        QPointF(200, 75),
        QPointF(200, 75),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    widget.wheelEvent(event)

    new_span = widget._view_end - widget._view_start
    assert new_span < initial_span
