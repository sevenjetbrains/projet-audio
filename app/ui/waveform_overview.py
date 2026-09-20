"""Bande de vue d'ensemble : tout le fichier en miniature, avec la fenêtre de zoom déplaçable."""

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.config.themes import Theme, get_theme
from app.workers.waveform_worker import WaveformWorker

_HEIGHT = 56
_LABEL = "VUE D'ENSEMBLE"
_WINDOW_ALPHA = 46
_RADIUS = 10.0


class WaveformOverview(QWidget):
    """Miniature du fichier entier ; cliquer ou glisser recadre la waveform principale."""

    view_requested = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._duration = 0.0
        self._peaks: np.ndarray | None = None
        self._view_start = 0.0
        self._view_end = 0.0
        self._worker: WaveformWorker | None = None
        self._theme: Theme = get_theme("")

    # --- API publique ---------------------------------------------------

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def load(self, wav_path: str, duration: float) -> None:
        """Calcule la miniature une fois pour toutes (elle ne dépend pas du zoom)."""
        self._duration = duration
        self._peaks = None
        self._view_start, self._view_end = 0.0, duration
        self.update()

        self._worker = WaveformWorker(wav_path, max(self.width(), 600))
        self._worker.peaks_ready.connect(self._on_peaks_ready)
        self._worker.failed.connect(lambda _message: self._on_peaks_ready(None))
        self._worker.start()

    def set_view_range(self, start: float, end: float) -> None:
        """Fenêtre actuellement affichée par la waveform principale."""
        self._view_start, self._view_end = start, end
        self.update()

    def _on_peaks_ready(self, peaks) -> None:
        self._peaks = peaks
        self.update()

    # --- Interaction ------------------------------------------------------

    def _recenter_on(self, x: float) -> None:
        """Déplace la fenêtre de zoom pour la centrer sur l'abscisse cliquée, sans changer sa largeur."""
        if self._duration <= 0:
            return
        span = self._view_end - self._view_start
        if span <= 0 or span >= self._duration:
            return
        center = max(0.0, min(x / max(self.width(), 1), 1.0)) * self._duration
        start = max(0.0, min(center - span / 2, self._duration - span))
        self.view_requested.emit(start, start + span)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._recenter_on(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._recenter_on(event.position().x())

    # --- Rendu ------------------------------------------------------------

    def _paint_label(self, painter: QPainter) -> None:
        font = QFont(painter.font())
        font.setPointSizeF(max(font.pointSizeF() - 2.0, 6.0))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._theme.color("text_faint")))
        painter.drawText(8, 14, _LABEL)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(self._theme.color("border")), 1))
        painter.setBrush(QColor(self._theme.waveform_background))
        painter.drawRoundedRect(frame, _RADIUS, _RADIUS)
        self._paint_label(painter)

        width = self.width()
        height = self.height()

        if self._peaks is not None and len(self._peaks) > 0:
            mid_y = height / 2
            count = len(self._peaks)
            painter.setPen(QColor(self._theme.waveform_color))
            for index in range(count):
                x = int(index * width / count)
                min_v, max_v = self._peaks[index]
                painter.drawLine(x, int(mid_y - float(max_v) * mid_y), x, int(mid_y - float(min_v) * mid_y))

        if self._duration > 0 and (self._view_end - self._view_start) < self._duration:
            x1 = self._view_start / self._duration * width
            x2 = self._view_end / self._duration * width
            accent = QColor(self._theme.color("overview_window"))
            fill = QColor(accent)
            fill.setAlpha(_WINDOW_ALPHA)
            painter.fillRect(QRectF(x1, 0, x2 - x1, height), fill)
            painter.setPen(QPen(accent, 1))
            painter.drawRect(QRectF(x1 + 0.5, 0.5, max(x2 - x1 - 1.0, 1.0), height - 1.0))

        painter.end()
