"""Briques visuelles partagées par les écrans : cartes, en-têtes de section, vignettes, boutons.

Le style réel vit dans `resources/styles/base.qss` ; ces fabriques ne posent que
le `objectName` ou la propriété dynamique que la feuille de style cible.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.icons import ICON_NAMES, set_button_icon, set_button_leading_icon


def card(variant: str = "true") -> QFrame:
    """Conteneur arrondi. `variant` : "true" (carte standard), "soft", "success"."""
    frame = QFrame()
    frame.setProperty("card", variant)
    return frame


def card_layout(variant: str = "true", spacing: int = 10, margin: int = 14) -> tuple[QFrame, QVBoxLayout]:
    """Carte prête à remplir, avec sa mise en page verticale déjà appliquée."""
    frame = card(variant)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    return frame, layout


def label(text: str, role: str = "mutedLabel") -> QLabel:
    """Libellé stylé par `objectName` : sectionLabel, titleLabel, mutedLabel, hintLabel, valueLabel…"""
    widget = QLabel(text)
    widget.setObjectName(role)
    return widget


def section_label(text: str) -> QLabel:
    """Titre de section, en capitales espacées comme dans la maquette (« LECTEUR VIDÉO »)."""
    return label(text.upper(), "sectionLabel")


def badge(text: str, tone: str = "neutral") -> QLabel:
    """Vignette compacte. `tone` : "neutral", "success", "accent"."""
    widget = QLabel(text)
    widget.setProperty("badge", tone)
    widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def set_badge_tone(widget: QLabel, tone: str) -> None:
    """Change la teinte d'une vignette déjà affichée (le style doit être réappliqué à la main)."""
    widget.setProperty("badge", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def section_header(text: str, trailing: QWidget | None = None) -> QWidget:
    """Ligne « TITRE DE SECTION …………… complément à droite »."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(section_label(text))
    layout.addStretch(1)
    if trailing is not None:
        layout.addWidget(trailing)
    return row


def accent_button(text: str) -> QPushButton:
    """Bouton d'action principale (orange plein)."""
    button = QPushButton(text)
    button.setProperty("accent", "true")
    return button


def kbd(text: str) -> QLabel:
    """Touche de clavier en pastille monospace (« Ctrl+O »), pour les aides de bas d'écran."""
    widget = QLabel(text)
    widget.setProperty("kbd", "true")
    widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return widget


def labelled_icon_button(text: str, icon: str, accent: bool = False) -> QPushButton:
    """Bouton « icône + libellé » (« 📁 Importer une vidéo… ») de l'écran d'accueil."""
    button = QPushButton(text)
    if accent:
        button.setProperty("accent", "true")
    set_button_leading_icon(button, icon, size=16)
    return button


def flat_button(text: str) -> QPushButton:
    """Bouton discret, sans fond ni bordure au repos."""
    button = QPushButton(text)
    button.setProperty("flat", "true")
    return button


def icon_button(icon: str, size: int = 34, flat: bool = False) -> QPushButton:
    """Bouton carré ne portant qu'une icône (lecture, stop, plein écran…).

    `icon` est le nom d'une icône vectorielle de `app.ui.icons` ; tout autre texte est affiché tel quel.
    """
    button = QPushButton()
    button.setFixedSize(size, size)
    button.setProperty("icon", "true")
    if flat:
        button.setProperty("flat", "true")
    if icon in ICON_NAMES:
        set_button_icon(button, icon)
    else:
        button.setText(icon)
    return button


def separator() -> QFrame:
    """Trait vertical de séparation dans une barre d'outils."""
    line = QFrame()
    line.setObjectName("toolBarSeparator")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    return line


def info_row(name: str, value: QLabel) -> QWidget:
    """Ligne « libellé ………… valeur », alignée comme le bloc SOURCE de la maquette."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(label(name, "mutedLabel"))
    layout.addStretch(1)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(value)
    return row
