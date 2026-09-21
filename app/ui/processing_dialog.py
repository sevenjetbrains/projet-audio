"""Fenêtre de traitement audio : hôte du panneau, sans chrome supplémentaire.

Le panneau porte lui-même l'en-tête, la colonne des profils et le pied de page de la
maquette ; la fenêtre ne fait que l'accueillir, sans marge, et reste non modale pour
qu'on puisse naviguer dans la waveform pendant qu'elle est ouverte.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from app.ui.audio_processing_panel import AudioProcessingPanel

# Tient dans la zone de travail d'un écran 1080p à 125 % ; au-delà, les cartes défilent
# plutôt que de comprimer la colonne des profils.
_MINIMUM_SIZE = (1120, 620)
_PREFERRED_SIZE = (1280, 900)


class ProcessingDialog(QDialog):
    """Fenêtre non modale contenant le panneau de traitement audio."""

    def __init__(self, panel: AudioProcessingPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traitement audio — AudioCut Studio")
        self.setModal(False)
        self.setMinimumSize(*_MINIMUM_SIZE)
        self.resize(*_PREFERRED_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel)
        panel.close_requested.connect(self.close)

    def show_and_raise(self) -> None:
        """Affiche la fenêtre, ou la ramène au premier plan si elle est déjà ouverte."""
        self.show()
        self.raise_()
        self.activateWindow()
