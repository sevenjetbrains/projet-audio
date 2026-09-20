"""Icônes vectorielles dessinées au QPainter.

Les glyphes Unicode (⏮, 🗑, 🔍…) dépendent de la police du système : à petite taille ils sortent
déformés ou absents selon la machine. Ces icônes sont tracées à la main, donc identiques partout,
nettes sur les écrans à forte densité et recolorées avec le thème courant.

Chaque bouton ou libellé enregistré par `set_button_icon` / `set_label_icon` est redessiné par
`set_icon_palette` quand le thème change.
"""

from collections.abc import Callable, Mapping
from weakref import WeakKeyDictionary

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QAbstractButton, QLabel
from shiboken6 import isValid

from app.config.palette import DARK_PALETTE

ICON_SIZE = 20  # côté logique de la grille de dessin, en pixels
_RENDER_SCALE = 2  # rendu en double résolution : nets sur les écrans à 125 % / 150 % / 200 %


# --- Dessins (grille 20 × 20) ------------------------------------------------------------------


def _polygon(points: list[tuple[float, float]]) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def _line(x1: float, y1: float, x2: float, y2: float) -> QPainterPath:
    path = QPainterPath(QPointF(x1, y1))
    path.lineTo(x2, y2)
    return path


def _speaker() -> QPainterPath:
    return _polygon([(3, 8), (6.5, 8), (11, 4), (11, 16), (6.5, 12), (3, 12)])


def _draw_play(p: QPainter) -> None:
    p.fillPath(_polygon([(6, 4), (16, 10), (6, 16)]), p.pen().color())


def _draw_pause(p: QPainter) -> None:
    p.fillRect(QRectF(5, 4, 3.6, 12), p.pen().color())
    p.fillRect(QRectF(11.4, 4, 3.6, 12), p.pen().color())


def _draw_stop(p: QPainter) -> None:
    path = QPainterPath()
    path.addRoundedRect(QRectF(5, 5, 10, 10), 1.5, 1.5)
    p.fillPath(path, p.pen().color())


def _draw_back(p: QPainter) -> None:
    color = p.pen().color()
    p.fillPath(_polygon([(10, 4), (3, 10), (10, 16)]), color)
    p.fillPath(_polygon([(17, 4), (10, 10), (17, 16)]), color)


def _draw_forward(p: QPainter) -> None:
    color = p.pen().color()
    p.fillPath(_polygon([(3, 4), (10, 10), (3, 16)]), color)
    p.fillPath(_polygon([(10, 4), (17, 10), (10, 16)]), color)


def _draw_undo(p: QPainter) -> None:
    arc = QPainterPath(QPointF(5, 9))
    arc.cubicTo(8, 4.5, 16, 4.5, 16, 11.5)
    arc.cubicTo(16, 15, 13, 16.5, 10, 16.5)
    p.drawPath(arc)
    p.drawPath(_line(5, 9, 5, 4.5))
    p.drawPath(_line(5, 9, 9.5, 9))


def _draw_redo(p: QPainter) -> None:
    p.setTransform(QTransform(-1, 0, 0, 1, ICON_SIZE, 0), True)  # symétrie horizontale de « annuler »
    _draw_undo(p)


def _draw_moon(p: QPainter) -> None:
    moon = QPainterPath()
    moon.addEllipse(QPointF(10, 10), 7, 7)
    bite = QPainterPath()
    bite.addEllipse(QPointF(13.5, 7.5), 6, 6)
    p.fillPath(moon.subtracted(bite), p.pen().color())


def _draw_lens(p: QPainter) -> None:
    p.drawEllipse(QPointF(8.5, 8.5), 5.5, 5.5)
    p.drawPath(_line(12.6, 12.6, 17, 17))


def _draw_zoom_in(p: QPainter) -> None:
    _draw_lens(p)
    p.drawPath(_line(6, 8.5, 11, 8.5))
    p.drawPath(_line(8.5, 6, 8.5, 11))


def _draw_zoom_out(p: QPainter) -> None:
    _draw_lens(p)
    p.drawPath(_line(6, 8.5, 11, 8.5))


def _draw_trash(p: QPainter) -> None:
    body = QPainterPath()
    body.addRoundedRect(QRectF(5.5, 7, 9, 10), 1.5, 1.5)
    p.drawPath(body)
    p.drawPath(_line(3.5, 5.5, 16.5, 5.5))
    p.drawPath(_line(8, 5.5, 8, 3.5))
    p.drawPath(_line(8, 3.5, 12, 3.5))
    p.drawPath(_line(12, 3.5, 12, 5.5))
    p.drawPath(_line(8.5, 9.5, 8.5, 14.5))
    p.drawPath(_line(11.5, 9.5, 11.5, 14.5))


def _draw_volume(p: QPainter) -> None:
    p.fillPath(_speaker(), p.pen().color())
    for radius in (3.2, 6.2):
        wave = QPainterPath()
        wave.arcMoveTo(QRectF(11.5 - radius, 10 - radius, 2 * radius, 2 * radius), 40)
        wave.arcTo(QRectF(11.5 - radius, 10 - radius, 2 * radius, 2 * radius), 40, -80)
        p.drawPath(wave)


def _draw_mute(p: QPainter) -> None:
    p.fillPath(_speaker(), p.pen().color())
    p.drawPath(_line(13.5, 7.5, 18, 12.5))
    p.drawPath(_line(18, 7.5, 13.5, 12.5))


def _draw_camera(p: QPainter) -> None:
    body = QPainterPath()
    body.addRoundedRect(QRectF(2.5, 6, 15, 10.5), 2, 2)
    p.drawPath(body)
    p.drawPath(_line(7, 6, 8, 4))
    p.drawPath(_line(8, 4, 12, 4))
    p.drawPath(_line(12, 4, 13, 6))
    p.drawEllipse(QPointF(10, 11.2), 3, 3)


def _draw_fullscreen(p: QPainter) -> None:
    for corner_x, corner_y, dx, dy in ((3.5, 3.5, 1, 1), (16.5, 3.5, -1, 1), (3.5, 16.5, 1, -1), (16.5, 16.5, -1, -1)):
        p.drawPath(_line(corner_x, corner_y, corner_x + 4.5 * dx, corner_y))
        p.drawPath(_line(corner_x, corner_y, corner_x, corner_y + 4.5 * dy))


_DRAWINGS: dict[str, Callable[[QPainter], None]] = {
    "play": _draw_play,
    "pause": _draw_pause,
    "stop": _draw_stop,
    "back": _draw_back,
    "forward": _draw_forward,
    "undo": _draw_undo,
    "redo": _draw_redo,
    "moon": _draw_moon,
    "zoom_in": _draw_zoom_in,
    "zoom_out": _draw_zoom_out,
    "trash": _draw_trash,
    "volume": _draw_volume,
    "mute": _draw_mute,
    "camera": _draw_camera,
    "fullscreen": _draw_fullscreen,
}

ICON_NAMES = frozenset(_DRAWINGS)


# --- Rendu ---------------------------------------------------------------------------------------


def render_icon(name: str, color: str | QColor, size: int = ICON_SIZE) -> QPixmap:
    """Pixmap de l'icône `name` à la couleur donnée (double résolution, transparent)."""
    if name not in _DRAWINGS:
        raise KeyError(f"Icône inconnue : {name}")
    pixmap = QPixmap(size * _RENDER_SCALE, size * _RENDER_SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(_RENDER_SCALE)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / ICON_SIZE, size / ICON_SIZE)
    pen = QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _DRAWINGS[name](painter)
    painter.end()
    return pixmap


# --- Enregistrement des widgets et couleurs du thème ---------------------------------------------

_palette: Mapping[str, str] = DARK_PALETTE
_registered: "WeakKeyDictionary[QObject, str]" = WeakKeyDictionary()


def _colors_for(widget: QObject) -> tuple[str, str]:
    """(couleur normale, couleur désactivée) : blanc sur les boutons d'accent, texte du thème sinon."""
    normal = "text_on_accent" if widget.property("accent") == "true" else "text"
    return _palette[normal], _palette["text_faint"]


def _two_state_icon(name: str, normal: str, disabled: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(render_icon(name, normal), QIcon.Mode.Normal)
    icon.addPixmap(render_icon(name, disabled), QIcon.Mode.Disabled)
    return icon


def _apply(widget: QObject, name: str) -> None:
    normal, disabled = _colors_for(widget)
    if isinstance(widget, QAbstractButton):
        widget.setText("")
        widget.setIcon(_two_state_icon(name, normal, disabled))
        widget.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    elif isinstance(widget, QAction):
        widget.setIcon(_two_state_icon(name, normal, disabled))
    elif isinstance(widget, QLabel):
        widget.setPixmap(render_icon(name, _palette["text_muted"]))


def set_button_icon(button: QAbstractButton, name: str) -> None:
    """Affiche l'icône `name` sur le bouton (à la place de son texte) et la suit lors des changements de thème."""
    _registered[button] = name
    _apply(button, name)


def set_action_icon(action: QAction, name: str) -> None:
    """Icône d'une QAction (les boutons de barre d'outils et les menus qui l'affichent la reprennent)."""
    _registered[action] = name
    _apply(action, name)


def set_label_icon(label: QLabel, name: str) -> None:
    """Affiche l'icône `name` dans un QLabel (icône décorative, teinte discrète)."""
    _registered[label] = name
    _apply(label, name)


def set_icon_palette(palette: Mapping[str, str]) -> None:
    """Change les couleurs d'icônes (thème clair/sombre) et redessine toutes les icônes enregistrées."""
    global _palette
    _palette = palette
    for widget, name in list(_registered.items()):
        if not isValid(widget):
            # L'objet Qt a été détruit (fenêtre fermée) alors que son wrapper Python survit encore.
            del _registered[widget]
            continue
        _apply(widget, name)
