"""Rendu d'une ligne de la liste des séquences : numéro, nom, bornes, vignette de statut.

La liste reste un QListWidget (glisser-déposer, sélection multiple) ; seul son
dessin est repris ici pour obtenir les colonnes et les vignettes de la maquette.
"""

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from app.config.themes import Theme, get_theme

ROW_DATA_ROLE = Qt.ItemDataRole.UserRole + 1

ROW_HEIGHT = 46
_NUMBER_WIDTH = 20
_START_WIDTH = 78
_DURATION_WIDTH = 66
_STATUS_WIDTH = 54
_PADDING = 10
_ACTIVE_BAR_WIDTH = 3


@dataclass(frozen=True)
class SequenceRow:
    """Ce qu'une ligne affiche, indépendamment du modèle métier."""

    number: int
    name: str
    start: str
    duration: str
    processed: bool


class SequenceRowDelegate(QStyledItemDelegate):
    """Dessine chaque séquence en colonnes NOM / DÉBUT / DURÉE / STATUT."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._theme: Theme = get_theme("")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter, option, index) -> None:
        row: SequenceRow | None = index.data(ROW_DATA_ROLE)
        if row is None:
            super().paint(painter, option, index)
            return

        palette = self._theme.palette
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        if selected:
            painter.setBrush(QColor(palette["card"]))
        elif hovered:
            painter.setBrush(QColor(palette["field"]))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # Filet accent à gauche : repère la séquence active, comme dans la maquette.
        if selected:
            painter.setBrush(QColor(palette["accent"]))
            painter.drawRect(QRectF(rect.left(), rect.top(), _ACTIVE_BAR_WIDTH, rect.height()))

        painter.setPen(QPen(QColor(palette["border"]), 1))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        self._paint_columns(painter, rect, row, palette)
        painter.restore()

    def _paint_columns(self, painter, rect, row: SequenceRow, palette) -> None:
        base_font = QFont(painter.font())
        mono = QFont("Consolas")
        mono.setPointSizeF(max(base_font.pointSizeF() - 1.0, 7.0))
        small = QFont(base_font)
        small.setPointSizeF(max(base_font.pointSizeF() - 1.0, 7.0))

        right = rect.right() - _PADDING
        status_x = right - _STATUS_WIDTH
        duration_x = status_x - _DURATION_WIDTH
        start_x = duration_x - _START_WIDTH
        number_x = rect.left() + _PADDING + _ACTIVE_BAR_WIDTH
        name_x = number_x + _NUMBER_WIDTH
        name_width = start_x - name_x - _PADDING

        painter.setFont(small)
        painter.setPen(QColor(palette["text_faint"]))
        painter.drawText(
            QRectF(number_x, rect.top(), _NUMBER_WIDTH, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(row.number),
        )

        painter.setFont(base_font)
        painter.setPen(QColor(palette["text"]))
        metrics = QFontMetrics(base_font)
        name = metrics.elidedText(row.name, Qt.TextElideMode.ElideRight, max(int(name_width), 10))
        painter.drawText(
            QRectF(name_x, rect.top(), max(name_width, 10), rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )

        painter.setFont(mono)
        painter.setPen(QColor(palette["text_muted"]))
        for x, width, text in (
            (start_x, _START_WIDTH, row.start),
            (duration_x, _DURATION_WIDTH, row.duration),
        ):
            painter.drawText(
                QRectF(x, rect.top(), width, rect.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )

        self._paint_status(painter, QRectF(status_x, rect.top(), _STATUS_WIDTH, rect.height()), row, palette)

    def _paint_status(self, painter, cell: QRectF, row: SequenceRow, palette) -> None:
        """Vignette « traité » (vert) ou « brut » (accent)."""
        text = "traité" if row.processed else "brut"
        color = QColor(palette["success"] if row.processed else palette["accent"])
        background = QColor(palette["success_soft"] if row.processed else palette["accent_soft"])

        font = QFont(painter.font())
        font.setPointSizeF(max(font.pointSizeF() - 0.5, 6.5))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        width = min(metrics.horizontalAdvance(text) + 14, cell.width())
        pill = QRectF(cell.left(), cell.center().y() - 9, width, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(pill, 9, 9)
        painter.setPen(color)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
