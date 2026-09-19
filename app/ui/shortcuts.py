"""Raccourcis clavier des boutons : un seul endroit pour lier touche, infobulle et libellé."""

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QAbstractButton


def set_button_shortcut(button: QAbstractButton, sequence: str, tooltip: str | None = None) -> None:
    """Associe un raccourci au bouton et l'indique dans son infobulle (« Supprimer la sélection (Suppr) »)."""
    key = QKeySequence(sequence)
    button.setShortcut(key)
    label = tooltip or button.text().strip()
    button.setToolTip(f"{label} ({key.toString(QKeySequence.SequenceFormat.NativeText)})")
