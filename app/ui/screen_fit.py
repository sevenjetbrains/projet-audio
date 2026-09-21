"""Adaptation des fenêtres à l'écran : aucune fenêtre ne doit dépasser la zone de travail, quelle que soit la résolution.

Une fenêtre réclamait une taille fixe (900 px de haut) : sur un écran 1080p à 125 % la zone de travail ne
mesure que 824 px, et le bas de la fenêtre — donc ses boutons d'action — se retrouvait sous la barre des tâches.

Règles appliquées à toutes les fenêtres :
- la taille demandée est plafonnée par la zone de travail de l'écran où la fenêtre s'ouvre (barre des tâches
  exclue), avec une marge et la place de la barre de titre ;
- la taille minimale n'est jamais supérieure à cette taille : sur un petit écran, le contenu défile ;
- la fenêtre est centrée sur la fenêtre parente (ou l'écran) puis ramenée entièrement dans la zone de travail.

Qt 6 exprime déjà `QScreen.availableGeometry()` en pixels logiques (ceux des widgets) : aucune division par le
facteur d'échelle, sinon un écran à 125 % serait pris pour un écran plus petit qu'il n'est.
"""

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QDialog, QWidget

SCREEN_MARGIN = 16  # espace laissé entre la fenêtre et chaque bord de la zone de travail
FRAME_ALLOWANCE = 44  # barre de titre et bordures que le système ajoute autour de la zone cliente
ABSOLUTE_MIN_SIZE = QSize(360, 260)  # en dessous, aucune mise en page n'est utilisable : on garde ce plancher


@dataclass(frozen=True)
class FittedSize:
    size: QSize
    minimum: QSize


def screen_of(widget: QWidget | None) -> QScreen | None:
    """Écran où s'ouvrira la fenêtre : celui de la fenêtre parente si elle existe, sinon l'écran principal."""
    if widget is not None:
        anchor = widget.window() if widget.window() is not None else widget
        screen = anchor.screen()
        if screen is not None:
            return screen
    return QGuiApplication.primaryScreen()


def available_rect(widget: QWidget | None = None) -> QRect:
    """Zone de travail (barre des tâches exclue) de l'écran concerné, en pixels logiques."""
    screen = screen_of(widget)
    return screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 720)


def available_size(widget: QWidget | None = None) -> tuple[int, int]:
    rect = available_rect(widget)
    return rect.width(), rect.height()


def fit_size(preferred: tuple[int, int], minimum: tuple[int, int], area: QRect) -> FittedSize:
    """Taille de fenêtre (zone cliente) qui tient dans `area`, et minimum jamais supérieur à cette taille."""
    max_width = max(area.width() - 2 * SCREEN_MARGIN, ABSOLUTE_MIN_SIZE.width())
    max_height = max(area.height() - FRAME_ALLOWANCE - SCREEN_MARGIN, ABSOLUTE_MIN_SIZE.height())
    width = min(preferred[0], max_width)
    height = min(preferred[1], max_height)
    return FittedSize(QSize(width, height), QSize(min(minimum[0], width), min(minimum[1], height)))


def position_within(size: QSize, area: QRect, around: QRect | None = None) -> QPoint:
    """Position à donner à `QWidget.move()` pour une fenêtre dont la zone cliente mesure `size`.

    `move()` place le cadre de la fenêtre, barre de titre comprise : le cadre occupe donc `size` plus la barre de
    titre (`FRAME_ALLOWANCE`). Il est centré sur `around` (ou sur `area`), puis ramené entièrement dans `area`.
    """
    reference = around if around is not None and not around.isEmpty() else area
    frame_height = size.height() + FRAME_ALLOWANCE
    edge = SCREEN_MARGIN // 2
    x = reference.center().x() - size.width() // 2
    y = reference.center().y() - frame_height // 2
    x = min(max(x, area.left() + edge), area.right() - size.width() - edge + 1)
    y = min(max(y, area.top() + edge), area.bottom() - frame_height - edge + 1)
    return QPoint(x, y)


class ScreenFittedDialog(QDialog):
    """Fenêtre de dialogue qui s'adapte à la zone de travail de l'écran où elle s'ouvre.

    Les classes dérivées fixent `PREFERRED_SIZE` et `MINIMUM_SIZE` (pixels logiques, pour un écran généreux) ; la
    taille réelle est recalculée à chaque ouverture, car la fenêtre peut s'ouvrir sur un autre écran que la fois
    précédente (résolution ou échelle différentes).
    """

    PREFERRED_SIZE: tuple[int, int] = (900, 640)
    MINIMUM_SIZE: tuple[int, int] = (640, 420)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._closed_size: QSize | None = None  # taille à la dernière fermeture : réutilisée à la réouverture
        self.fit_to_screen()

    def fit_to_screen(self) -> None:
        """Applique la taille adaptée à l'écran courant (sans toucher à la position)."""
        fitted = fit_size(self.PREFERRED_SIZE, self.MINIMUM_SIZE, available_rect(self.parentWidget() or self))
        self.setMinimumSize(fitted.minimum)
        self.resize(fitted.size)

    def showEvent(self, event) -> None:
        if not event.spontaneous():  # ouverture (show), pas une simple restauration après minimisation
            self._place_on_screen()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        if not event.spontaneous() and not self.isMinimized():
            self._closed_size = self.size()
        super().hideEvent(event)

    def _place_on_screen(self) -> None:
        parent = self.parentWidget().window() if self.parentWidget() is not None else None
        area = available_rect(parent or self)
        fitted = fit_size(self.PREFERRED_SIZE, self.MINIMUM_SIZE, area)
        target = fitted.size
        if self._closed_size is not None:
            # Taille choisie par l'utilisateur à la dernière fermeture, ramenée dans l'écran courant si besoin.
            target = QSize(min(self._closed_size.width(), fitted.size.width()), min(self._closed_size.height(), fitted.size.height()))
        self.setMinimumSize(fitted.minimum)
        self.resize(target)
        around = parent.frameGeometry() if parent is not None and parent.isVisible() else None
        self.move(position_within(target, area, around))
