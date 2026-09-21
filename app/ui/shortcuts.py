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
        ("L", "Activer / désactiver la boucle de la sélection"),
        ("F", "Plein écran de la vidéo (Échap ou F pour quitter)"),
        ("F11", "Plein écran de la vidéo"),
        ("Ctrl+Space", "Arrêter la lecture"),
        ("Alt+Left", "Reculer de 5 s"),
        ("Alt+Right", "Avancer de 5 s"),
        ("I", "Marquer le début de la sélection à la position de lecture"),
        ("O", "Marquer la fin de la sélection à la position de lecture"),
        ("Return", "Créer une séquence depuis la sélection"),
    ],
    "Repères": [
        ("M", "Poser un repère à la position de lecture"),
        ("Shift+M", "Retirer le repère sous la tête de lecture"),
        ("Alt+Up", "Aller au repère précédent"),
        ("Alt+Down", "Aller au repère suivant"),
        ("Alt+S", "Sélectionner l'intervalle entre les deux repères encadrants"),
    ],
    "Séquences": [
        ("Ctrl+L", "Lire la séquence"),
        ("F2", "Renommer"),
        ("F3", "Ajuster les bornes de la séquence (poignées sur la waveform)"),
        ("Ctrl+B", "Comparer : écouter la version originale ou traitée (A/B)"),
        ("S", "Diviser la séquence à la tête de lecture"),
        ("Ctrl+D", "Dupliquer"),
        ("Delete", "Supprimer"),
        ("Ctrl+M", "Fusionner et prévisualiser"),
    ],
    "Traitement audio": [
        ("Ctrl+Return", "Appliquer le traitement (à la sélection entière si elle en compte plusieurs)"),
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
