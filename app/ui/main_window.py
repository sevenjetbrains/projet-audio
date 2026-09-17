"""Fenêtre principale minimale d'AudioCut Studio (squelette, sans logique métier)."""

from PySide6.QtWidgets import QLabel, QMainWindow

from app.config.constants import APP_NAME


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        placeholder = QLabel("AudioCut Studio — squelette du projet.\nImport vidéo à venir (Phase 2).")
        placeholder.setContentsMargins(24, 24, 24, 24)
        self.setCentralWidget(placeholder)
