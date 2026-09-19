"""Widget waveform custom (QPainter) : affichage, sélection à la souris, zoom, tête de lecture."""

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from app.audio.waveform import compute_peaks
from app.config.themes import THEMES, Theme, get_theme
from app.workers.waveform_worker import WaveformWorker

_DRAG_THRESHOLD_PX = 4
_MIN_VIEW_SPAN_SECONDS = 0.2
_ZOOM_IN_FACTOR = 0.8
_ZOOM_OUT_FACTOR = 1.25
# Teintes (HSV) des séquences déjà créées, alternées pour distinguer deux séquences voisines.
_REGION_HUES = (30, 130, 280, 340, 190, 60)
_REGION_ALPHA = 55


class WaveformWidget(QWidget):
    seek_requested = Signal(float)
    selection_changed = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setMouseTracking(False)

        self._wav_path: str | None = None
        self._duration = 0.0
        self._view_start = 0.0
        self._view_end = 0.0
        self._peaks: np.ndarray | None = None
        self._status_text = "Aucune waveform à afficher."

        self._playhead = 0.0
        self._selection: tuple[float, float] | None = None
        self._regions: list[tuple[float, float, str]] = []
        self._pending_selection: tuple[float, float] | None = None
        self._drag_start_x: float | None = None
        self._dragging = False

        self._worker: WaveformWorker | None = None
        self._theme: Theme = get_theme("")

    # --- API publique ---------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def load(self, wav_path: str, duration: float) -> None:
        self._wav_path = wav_path
        self._duration = duration
        self._view_start = 0.0
        self._view_end = duration
        self._peaks = None
        self._selection = None
        self._playhead = 0.0
        self._status_text = "Chargement de la waveform…"
        self.update()

        target_width = max(self.width(), 400)
        self._worker = WaveformWorker(wav_path, target_width)
        self._worker.peaks_ready.connect(self._on_peaks_ready)
        self._worker.failed.connect(self._on_peaks_failed)
        self._worker.start()

    def set_sequence_regions(self, regions: list[tuple[float, float, str]]) -> None:
        """Séquences existantes (début, fin en secondes de la source, nom) affichées en zones colorées."""
        self._regions = list(regions)
        self.update()

    def set_playhead(self, seconds: float) -> None:
        self._playhead = seconds
        self.update()

    def set_selection(self, start: float, end: float) -> None:
        if start > end:
            start, end = end, start
        self._selection = (start, end)
        self.update()

    # --- Chargement des peaks --------------------------------------------

    def _on_peaks_ready(self, peaks: np.ndarray) -> None:
        self._peaks = peaks
        self._status_text = ""
        self.update()

    def _on_peaks_failed(self, message: str) -> None:
        self._peaks = None
        self._status_text = message
        self.update()

    def _recompute_peaks_sync(self) -> None:
        if not self._wav_path:
            return
        target_width = max(self.width(), 1)
        self._peaks = compute_peaks(self._wav_path, target_width, self._view_start, self._view_end)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._wav_path and self._peaks is not None:
            self._recompute_peaks_sync()

    # --- Conversions temps <-> pixels ------------------------------------

    def _time_to_x(self, seconds: float) -> float:
        span = max(self._view_end - self._view_start, 1e-9)
        return (seconds - self._view_start) / span * self.width()

    def _x_to_time(self, x: float) -> float:
        span = self._view_end - self._view_start
        ratio = x / max(self.width(), 1)
        return self._view_start + ratio * span

    # --- Interaction souris ------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._duration <= 0:
            return
        self._drag_start_x = event.position().x()
        self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start_x is None:
            return
        current_x = event.position().x()
        if not self._dragging and abs(current_x - self._drag_start_x) < _DRAG_THRESHOLD_PX:
            return
        self._dragging = True
        start_t = self._x_to_time(min(self._drag_start_x, current_x))
        end_t = self._x_to_time(max(self._drag_start_x, current_x))
        self._pending_selection = (
            max(0.0, min(start_t, end_t)),
            min(self._duration, max(start_t, end_t)),
        )
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start_x is None:
            return
        if self._dragging and self._pending_selection is not None:
            self._selection = self._pending_selection
            self.selection_changed.emit(*self._selection)
        else:
            seek_time = min(max(self._x_to_time(event.position().x()), 0.0), self._duration)
            self.seek_requested.emit(seek_time)

        self._drag_start_x = None
        self._dragging = False
        self._pending_selection = None
        self.update()

    def wheelEvent(self, event) -> None:
        if self._duration <= 0:
            return

        zoom_factor = _ZOOM_IN_FACTOR if event.angleDelta().y() > 0 else _ZOOM_OUT_FACTOR
        mouse_time = self._x_to_time(event.position().x())
        current_span = self._view_end - self._view_start
        new_span = max(min(current_span * zoom_factor, self._duration), _MIN_VIEW_SPAN_SECONDS)

        ratio = (mouse_time - self._view_start) / current_span if current_span > 0 else 0.5
        new_start = mouse_time - ratio * new_span
        new_end = new_start + new_span

        if new_start < 0:
            new_start, new_end = 0.0, new_span
        if new_end > self._duration:
            new_end = self._duration
            new_start = max(0.0, new_end - new_span)

        self._view_start, self._view_end = new_start, new_end
        self._recompute_peaks_sync()
        event.accept()

    # --- Rendu -------------------------------------------------------------

    def _paint_regions(self, painter: QPainter, width: int, height: int) -> None:
        metrics = QFontMetrics(painter.font())
        for index, (start, end, name) in enumerate(self._regions):
            x1 = max(self._time_to_x(start), 0.0)
            x2 = min(self._time_to_x(end), float(width))
            if x2 <= x1:
                continue  # hors de la zone visible (zoom)
            color = QColor.fromHsv(_REGION_HUES[index % len(_REGION_HUES)], 200, 230, _REGION_ALPHA)
            painter.fillRect(QRectF(x1, 0, x2 - x1, height), color)

            label_width = int(x2 - x1) - 6
            if label_width > 12:
                painter.setPen(QColor(self._theme.waveform_text))
                text = metrics.elidedText(name, Qt.TextElideMode.ElideRight, label_width)
                painter.drawText(int(x1) + 3, metrics.ascent() + 2, text)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._theme.waveform_background))

        if self._peaks is None or len(self._peaks) == 0:
            painter.setPen(QColor(self._theme.waveform_text))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._status_text)
            painter.end()
            return

        width = self.width()
        height = self.height()
        mid_y = height / 2
        n = len(self._peaks)

        self._paint_regions(painter, width, height)

        sel = self._pending_selection if self._dragging else self._selection
        if sel:
            x1 = self._time_to_x(sel[0])
            x2 = self._time_to_x(sel[1])
            painter.fillRect(QRectF(x1, 0, x2 - x1, height), QColor(79, 195, 247, 60))

        painter.setPen(QColor(self._theme.waveform_color))
        for i in range(n):
            x = int(i * width / n)
            min_v, max_v = self._peaks[i]
            y1 = mid_y - float(max_v) * mid_y
            y2 = mid_y - float(min_v) * mid_y
            painter.drawLine(x, int(y1), x, int(y2))

        if self._duration > 0:
            px = self._time_to_x(self._playhead)
            if 0 <= px <= width:
                painter.setPen(QColor(self._theme.playhead_color))
                painter.drawLine(int(px), 0, int(px), height)

        painter.end()
