"""Barre d'outils principale : les actions les plus fréquentes, groupées comme dans la maquette.

Chaque bouton est adossé à la QAction du menu correspondant (`setDefaultAction`) :
le libellé, l'infobulle, l'état activé et le raccourci restent définis une seule fois.
"""

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from app.ui.design import separator
from app.ui.icons import ICON_NAMES, set_action_icon

ACCENT_PROPERTY = "accent"
LABEL_PROPERTY = "toolbar_label"
ICON_PROPERTY = "toolbar_icon"


def _button(action: QAction) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    icon_name = action.property(ICON_PROPERTY)
    if icon_name in ICON_NAMES:
        # L'icône est portée par l'action : le bouton la garde même quand l'action change de texte (annuler/refaire).
        set_action_icon(action, icon_name)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setProperty("icon", "true")
    else:
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if action.property(ACCENT_PROPERTY):
        button.setProperty(ACCENT_PROPERTY, "true")
    # Libellé court propre à la barre d'outils (« Importer » au lieu de « Importer une vidéo… »).
    short_label = action.property(LABEL_PROPERTY)
    if short_label and icon_name not in ICON_NAMES:
        button.setText(short_label)
    return button


class AppToolBar(QWidget):
    """Barre horizontale de groupes d'actions, avec un groupe aligné à droite."""

    def __init__(
        self,
        groups: Sequence[Sequence[QAction]],
        trailing: Sequence[QAction] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toolBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        for index, group in enumerate(groups):
            if index:
                layout.addWidget(separator())
            for action in group:
                layout.addWidget(_button(action))

        layout.addStretch(1)
        for action in trailing:
            layout.addWidget(_button(action))
