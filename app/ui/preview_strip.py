"""Bande « avant / après » : les deux versions d'un extrait côte à côte, et la tête de lecture.

La moitié gauche montre l'extrait brut en gris, la droite le même extrait traité en accent :
on compare d'un coup d'œil ce que les réglages ont changé, et on suit à l'oreille pendant
que la tête traverse les deux moitiés.
"""

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app.config.themes import Theme, get_theme

_GAP_PX = 14  # séparation entre les deux moitiés, pour qu'on voie où l'une finit
_MIN_BAR_HEIGHT = 1.0


class BeforeAfterStrip(QWidget):
    """Deux formes d'onde accolées ; `set_progress` place la tête de lecture sur l'ensemble."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(56)
        self._before: np.ndarray | None = None
        self._after: np.ndarray | None = None
        self._progress: float | None = None
        self._theme: Theme = get_theme("")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_peaks(self, before: np.ndarray | None, after: np.ndarray | None) -> None:
        self._before, self._after = before, after
        self.update()

    def set_progress(self, progress: float | None) -> None:
        """Avancement de l'écoute sur les deux moitiés (0 à 1), ou None pour cacher la tête."""
        self._progress = progress
        self.update()

    @property
    def has_peaks(self) -> bool:
        return self._before is not None and self._after is not None

    def clear(self) -> None:
        self.set_peaks(None, None)
        self.set_progress(None)

    def _paint_half(self, painter: QPainter, peaks: np.ndarray, left: float, width: float, colour: QColor) -> None:
        if width <= 0 or len(peaks) == 0:
            return
        middle = self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        count = len(peaks)
        bar_width = max(width / count * 0.62, 1.0)
        for index in range(count):
            amplitude = float(max(abs(peaks[index][0]), abs(peaks[index][1])))
            height = max(amplitude * (self.height() - 6), _MIN_BAR_HEIGHT)
            x = left + index * width / count
            painter.drawRoundedRect(QRectF(x, middle - height / 2, bar_width, height), 1, 1)

    def paintEvent(self, _event) -> None:
        if not self.has_peaks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        half = (self.width() - _GAP_PX) / 2
        self._paint_half(painter, self._before, 0.0, half, QColor(self._theme.color("wave_bar")))
        self._paint_half(painter, self._after, half + _GAP_PX, half, QColor(self._theme.color("accent")))

        if self._progress is not None:
            x = min(max(self._progress, 0.0), 1.0) * self.width()
            painter.fillRect(QRectF(x - 1, 0, 2, self.height()), QColor(self._theme.playhead_color))
        painter.end()
