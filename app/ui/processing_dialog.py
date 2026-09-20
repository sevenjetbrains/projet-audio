"""Fenêtre de traitement audio : accueille le panneau de traitement hors de la fenêtre principale.

La maquette de la fenêtre principale n'affiche plus le panneau en permanence, mais
un bouton « Appliquer un traitement… » ; le panneau vit donc dans cette fenêtre,
non modale, pour rester utilisable pendant qu'on navigue dans la waveform.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from app.ui.audio_processing_panel import AudioProcessingPanel


class ProcessingDialog(QDialog):
    """Fenêtre non modale contenant le panneau de traitement audio."""

    def __init__(self, panel: AudioProcessingPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traitement audio — AudioCut Studio")
        self.setModal(False)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(panel)

    def show_and_raise(self) -> None:
        """Affiche la fenêtre, ou la ramène au premier plan si elle est déjà ouverte."""
        self.show()
        self.raise_()
        self.activateWindow()
