"""Widget waveform custom (QPainter) : affichage, sélection à la souris, zoom, tête de lecture.

Rendu conforme à la maquette : chaque séquence est une boîte arrondie étiquetée,
la séquence sélectionnée passe en accent, et une règle temporelle occupe le bas.
"""

from typing import NamedTuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from app.audio.waveform import compute_peaks
from app.config.themes import Theme, get_theme
from app.workers.waveform_worker import WaveformWorker

_DRAG_THRESHOLD_PX = 4
_MIN_VIEW_SPAN_SECONDS = 0.2
_ZOOM_IN_FACTOR = 0.8
_ZOOM_OUT_FACTOR = 1.25

_RULER_HEIGHT = 24
_PANEL_RADIUS = 10.0
_REGION_INSET_PX = 2.0
_REGION_RADIUS = 6.0
_LABEL_PILL_HEIGHT = 18
_SELECTION_ALPHA = 48
_REGION_FILL_ALPHA = 190
# Paliers de graduation de la règle temporelle, du plus fin au plus large (secondes).
_TICK_STEPS = (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600)


class SequenceRegion(NamedTuple):
    """Zone d'une séquence sur la forme d'onde (temps en secondes dans l'audio source)."""

    start: float
    end: float
    name: str
    sequence_id: str = ""


def _nice_tick_step(span: float, width: int) -> float:
    """Pas de graduation le plus fin qui laisse au moins 70 px entre deux étiquettes."""
    minimum = span * 70 / max(width, 1)
    for step in _TICK_STEPS:
        if step >= minimum:
            return float(step)
    return float(_TICK_STEPS[-1])


def _tick_text(seconds: float, step: float) -> str:
    """Étiquette de graduation : `MM:SS` (ou `MM:SS,m` quand le pas descend sous la seconde)."""
    minutes, secs = divmod(seconds, 60)
    if step < 1:
        return f"{int(minutes):02d}:{secs:04.1f}".replace(".", ",")
    return f"{int(minutes):02d}:{int(secs):02d}"


class WaveformWidget(QWidget):
    seek_requested = Signal(float)
    region_clicked = Signal(str)
    region_double_clicked = Signal(str)
    selection_changed = Signal(float, float)
    view_changed = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setMouseTracking(False)

        self._wav_path: str | None = None
        self._duration = 0.0
        self._view_start = 0.0
        self._view_end = 0.0
        self._peaks: np.ndarray | None = None
        self._status_text = "Aucune waveform à afficher."

        self._playhead = 0.0
        self._selection: tuple[float, float] | None = None
        self._regions: list[SequenceRegion] = []
        self._active_sequence_id = ""
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
        self.view_changed.emit(self._view_start, self._view_end)

        target_width = max(self.width(), 400)
        self._worker = WaveformWorker(wav_path, target_width)
        self._worker.peaks_ready.connect(self._on_peaks_ready)
        self._worker.failed.connect(self._on_peaks_failed)
        self._worker.start()

    def set_sequence_regions(self, regions: list[tuple]) -> None:
        """Séquences existantes (début, fin, nom[, id]) affichées en zones colorées et cliquables."""
        self._regions = [SequenceRegion(*region) for region in regions]
        self.update()

    def set_active_sequence(self, sequence_id: str) -> None:
        """Met en accent la zone de la séquence sélectionnée dans la liste."""
        self._active_sequence_id = sequence_id or ""
        self.update()

    def region_at(self, seconds: float) -> SequenceRegion | None:
        """Séquence affichée au-dessus des autres au temps donné (la dernière dessinée), ou None."""
        for region in reversed(self._regions):
            if region.start <= seconds <= region.end:
                return region
        return None

    def set_playhead(self, seconds: float) -> None:
        self._playhead = seconds
        self.update()

    def set_selection(self, start: float, end: float) -> None:
        if start > end:
            start, end = end, start
        self._selection = (start, end)
        self.update()

    # --- Zoom et cadrage --------------------------------------------------

    @property
    def view_range(self) -> tuple[float, float]:
        return self._view_start, self._view_end

    @property
    def zoom_factor(self) -> float:
        """Rapport entre la durée totale et la portion visible (1,0 = tout le fichier)."""
        span = self._view_end - self._view_start
        if span <= 0 or self._duration <= 0:
            return 1.0
        return self._duration / span

    def set_view_range(self, start: float, end: float) -> None:
        """Cadre la vue sur [start, end], borné à l'audio et à la portée minimale."""
        if self._duration <= 0:
            return
        span = max(min(end - start, self._duration), _MIN_VIEW_SPAN_SECONDS)
        start = max(0.0, min(start, self._duration - span))
        self._view_start, self._view_end = start, start + span
        self._recompute_peaks_sync()
        self.view_changed.emit(self._view_start, self._view_end)

    def zoom_in(self) -> None:
        self._zoom_around(self._view_center, _ZOOM_IN_FACTOR)

    def zoom_out(self) -> None:
        self._zoom_around(self._view_center, _ZOOM_OUT_FACTOR)

    def reset_zoom(self) -> None:
        """Réaffiche l'intégralité du fichier."""
        if self._duration > 0:
            self.set_view_range(0.0, self._duration)

    @property
    def _view_center(self) -> float:
        return (self._view_start + self._view_end) / 2.0

    def _zoom_around(self, pivot_seconds: float, factor: float) -> None:
        """Zoom conservant `pivot_seconds` à sa position relative dans la vue."""
        if self._duration <= 0:
            return
        current_span = self._view_end - self._view_start
        new_span = max(min(current_span * factor, self._duration), _MIN_VIEW_SPAN_SECONDS)
        ratio = (pivot_seconds - self._view_start) / current_span if current_span > 0 else 0.5
        self.set_view_range(pivot_seconds - ratio * new_span, pivot_seconds - ratio * new_span + new_span)

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
            self.update()
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

    @property
    def _wave_height(self) -> int:
        """Hauteur de la zone d'onde, la règle temporelle occupant le bas du widget."""
        return max(self.height() - _RULER_HEIGHT, 1)

    # --- Interaction souris ------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._duration <= 0:
            return
        self._drag_start_x = event.position().x()
        self._dragging = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._duration <= 0:
            return
        region = self.region_at(min(max(self._x_to_time(event.position().x()), 0.0), self._duration))
        if region is not None and region.sequence_id:
            self.region_double_clicked.emit(region.sequence_id)
        # Le relâchement qui suit ce double-clic ne doit pas être traité comme un nouveau clic simple.
        self._drag_start_x = None
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
            region = self.region_at(seek_time)
            if region is not None and region.sequence_id:
                self.region_clicked.emit(region.sequence_id)

        self._drag_start_x = None
        self._dragging = False
        self._pending_selection = None
        self.update()

    def wheelEvent(self, event) -> None:
        if self._duration <= 0:
            return
        zoom_factor = _ZOOM_IN_FACTOR if event.angleDelta().y() > 0 else _ZOOM_OUT_FACTOR
        self._zoom_around(self._x_to_time(event.position().x()), zoom_factor)
        event.accept()

    # --- Rendu -------------------------------------------------------------

    def _paint_panel(self, painter: QPainter) -> None:
        """Fond arrondi et bordure de la carte, pour que le widget se fonde dans la maquette."""
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(self._theme.color("border")), 1))
        painter.setBrush(QColor(self._theme.waveform_background))
        painter.drawRoundedRect(frame, _PANEL_RADIUS, _PANEL_RADIUS)

    def _region_colors(self, region: SequenceRegion) -> tuple[QColor, QColor]:
        """Couleurs (remplissage, bordure) d'une zone, en accent si c'est la séquence sélectionnée."""
        active = bool(region.sequence_id) and region.sequence_id == self._active_sequence_id
        suffix = "_active" if active else ""
        fill = QColor(self._theme.color(f"region_fill{suffix}"))
        fill.setAlpha(_REGION_FILL_ALPHA)
        return fill, QColor(self._theme.color(f"region_border{suffix}"))

    def _paint_region_label(self, painter: QPainter, region: SequenceRegion, x1: float, x2: float) -> None:
        """Étiquette de la séquence, en pastille dans le coin haut gauche de sa zone."""
        available = x2 - x1 - 12
        if available < 24:
            return
        _fill, border = self._region_colors(region)
        font = QFont(painter.font())
        font.setPointSizeF(max(font.pointSizeF() - 1.0, 6.0))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text = metrics.elidedText(region.name, Qt.TextElideMode.ElideRight, int(available) - 12)

        pill_width = min(metrics.horizontalAdvance(text) + 14, available)
        pill = QRectF(x1 + 6, 6, pill_width, _LABEL_PILL_HEIGHT)
        pill_fill = QColor(border)
        pill_fill.setAlpha(55)
        painter.setPen(QPen(border, 1))
        painter.setBrush(pill_fill)
        painter.drawRoundedRect(pill, 5, 5)
        painter.setPen(border)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_regions(self, painter: QPainter, width: int, height: int) -> None:
        painter.save()
        for region in self._regions:
            x1 = max(self._time_to_x(region.start) + _REGION_INSET_PX, 0.0)
            x2 = min(self._time_to_x(region.end) - _REGION_INSET_PX, float(width))
            if x2 <= x1:
                continue  # hors de la zone visible (zoom) ou trop étroite pour être dessinée
            fill, border = self._region_colors(region)
            box = QRectF(x1, 0.5, x2 - x1, height - 1.0)
            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(box, _REGION_RADIUS, _REGION_RADIUS)
            self._paint_region_label(painter, region, x1, x2)
        painter.restore()

    def _paint_bars(self, painter: QPainter, width: int, height: int) -> None:
        mid_y = height / 2
        count = len(self._peaks)
        painter.setPen(QColor(self._theme.waveform_color))
        for index in range(count):
            x = int(index * width / count)
            min_v, max_v = self._peaks[index]
            y1 = mid_y - float(max_v) * mid_y
            y2 = mid_y - float(min_v) * mid_y
            painter.drawLine(x, int(y1), x, int(y2))

    def _paint_ruler(self, painter: QPainter, width: int, height: int) -> None:
        """Graduations et étiquettes de temps sous la zone d'onde."""
        span = self._view_end - self._view_start
        if span <= 0:
            return
        painter.save()
        step = _nice_tick_step(span, width)
        color = QColor(self._theme.waveform_text)
        grid = QColor(self._theme.color("wave_grid"))
        font = QFont(painter.font())
        font.setPointSizeF(max(font.pointSizeF() - 1.5, 6.0))
        painter.setFont(font)
        metrics = QFontMetrics(font)

        first_tick = (int(self._view_start / step)) * step
        tick = first_tick
        while tick <= self._view_end + step:
            x = self._time_to_x(tick)
            if 0 <= x <= width and tick >= 0:
                painter.setPen(QPen(grid, 1))
                painter.drawLine(int(x), height, int(x), height + 4)
                text = _tick_text(tick, step)
                text_width = metrics.horizontalAdvance(text)
                text_x = min(max(x - text_width / 2, 0.0), width - text_width)
                painter.setPen(color)
                painter.drawText(int(text_x), height + 6 + metrics.ascent(), text)
            tick += step
        painter.restore()

    def _paint_playhead(self, painter: QPainter, width: int, height: int) -> None:
        x = self._time_to_x(self._playhead)
        if not 0 <= x <= width:
            return
        color = QColor(self._theme.playhead_color)
        painter.setPen(QPen(color, 1))
        painter.drawLine(int(x), 0, int(x), height)
        # Poignée triangulaire, comme dans la maquette, pour rendre la tête de lecture saisissable à l'œil.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([
            QPointF(x - 5, 0),
            QPointF(x + 5, 0),
            QPointF(x, 7),
        ]))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_panel(painter)

        if self._peaks is None or len(self._peaks) == 0:
            painter.setPen(QColor(self._theme.waveform_text))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._status_text)
            painter.end()
            return

        width = self.width()
        height = self._wave_height

        self._paint_regions(painter, width, height)

        # L'onde et la sélection restent confinées à la zone d'onde, au-dessus de la règle.
        painter.save()
        clip = QPainterPath()
        clip.addRect(QRectF(0, 0, width, height))
        painter.setClipPath(clip)

        self._paint_bars(painter, width, height)

        selection = self._pending_selection if self._dragging else self._selection
        if selection:
            x1 = self._time_to_x(selection[0])
            x2 = self._time_to_x(selection[1])
            fill = QColor(self._theme.color("selection_fill"))
            fill.setAlpha(_SELECTION_ALPHA)
            painter.fillRect(QRectF(x1, 0, x2 - x1, height), fill)

        if self._duration > 0:
            self._paint_playhead(painter, width, height)
        painter.restore()

        self._paint_ruler(painter, width, height)
        painter.end()
