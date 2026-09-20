"""Raccourcis clavier des boutons : un seul endroit pour lier touche, infobulle et libellé."""

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QAbstractButton


def set_button_shortcut(button: QAbstractButton, sequence: str, tooltip: str | None = None) -> None:
    """Associe un raccourci au bouton et l'indique dans son infobulle (« Supprimer la sélection (Suppr) »)."""
    key = QKeySequence(sequence)
    button.setShortcut(key)
    label = tooltip or button.text().strip()
    button.setToolTip(f"{label} ({key.toString(QKeySequence.SequenceFormat.NativeText)})")


# (touche Qt, description) regroupés par thème : source unique de la fenêtre d'aide.
SHORTCUTS_HELP: dict[str, list[tuple[str, str]]] = {
    "Projet": [
        ("Ctrl+O", "Importer une vidéo"),
        ("Ctrl+Shift+O", "Ouvrir un projet"),
        ("Ctrl+S", "Sauvegarder le projet"),
        ("Ctrl+E", "Exporter"),
        ("Ctrl+Z", "Annuler"),
        ("Ctrl+Y", "Refaire"),
    ],
    "Lecture et sélection": [
        ("Space", "Lecture / pause"),
        ("Shift+Space", "Écouter uniquement la sélection"),
        ("F", "Plein écran de la vidéo (Échap ou F pour quitter)"),
        ("F11", "Plein écran de la vidéo"),
        ("Ctrl+Space", "Arrêter la lecture"),
        ("Alt+Left", "Reculer de 5 s"),
        ("Alt+Right", "Avancer de 5 s"),
        ("I", "Marquer le début de la sélection à la position de lecture"),
        ("O", "Marquer la fin de la sélection à la position de lecture"),
        ("Return", "Créer une séquence depuis la sélection"),
    ],
    "Séquences": [
        ("Ctrl+L", "Lire la séquence"),
        ("F2", "Renommer"),
        ("Ctrl+D", "Dupliquer"),
        ("Delete", "Supprimer"),
        ("Ctrl+M", "Fusionner et prévisualiser"),
    ],
    "Traitement audio": [
        ("Ctrl+Return", "Appliquer à la séquence"),
        ("Ctrl+Shift+Return", "Appliquer à la sélection"),
        ("Ctrl+R", "Réinitialiser le traitement"),
    ],
    "Aide": [("F1", "Afficher cette liste")],
}


def shortcuts_help_html() -> str:
    """Tableau HTML des raccourcis, avec les touches au format natif de la plateforme."""
    rows = []
    for group, entries in SHORTCUTS_HELP.items():
        rows.append(f"<tr><td colspan='2'><b>{group}</b></td></tr>")
        for key, description in entries:
            native = QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)
            rows.append(f"<tr><td style='padding-right:16px'><code>{native}</code></td><td>{description}</td></tr>")
    return f"<table cellspacing='4'>{''.join(rows)}</table>"
