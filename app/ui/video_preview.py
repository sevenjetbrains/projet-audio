"""Aperçu vidéo : QVideoWidget, avec un message d'attente tant qu'aucune vidéo n'est chargée."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget

from app.config.settings import TEMP_DIR

_PLACEHOLDER = "▶\nimage de la vidéo"


class VideoPreview(QWidget):
    """Sortie vidéo du lecteur : permet de visualiser la vidéo pour repérer les passages à extraire."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self._snapshot_dir = TEMP_DIR

        self._video_widget = QVideoWidget()
        self._placeholder = QLabel(_PLACEHOLDER)
        self._placeholder.setObjectName("hintLabel")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._stack = QStackedLayout()
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._video_widget)
        self.setLayout(self._stack)

    @property
    def video_widget(self) -> QVideoWidget:
        return self._video_widget

    @property
    def is_active(self) -> bool:
        return self._stack.currentWidget() is self._video_widget

    def set_active(self, active: bool) -> None:
        """Bascule entre l'image vidéo et le message d'attente."""
        self._stack.setCurrentWidget(self._video_widget if active else self._placeholder)

    def set_snapshot_dir(self, directory: str) -> None:
        """Dossier où écrire les captures d'image (le dossier temporaire du projet ouvert)."""
        if directory:
            self._snapshot_dir = Path(directory)

    def toggle_fullscreen(self) -> None:
        """Passe la seule image vidéo en plein écran, ou en revient (Échap fonctionne aussi)."""
        self._video_widget.setFullScreen(not self._video_widget.isFullScreen())

    def save_snapshot(self) -> Path | None:
        """Écrit l'image actuellement affichée en PNG et retourne son chemin, ou None en cas d'échec.

        La capture passe par le rendu du widget : selon le backend multimédia, la
        surface vidéo peut être composée hors de Qt et l'image obtenue être vide.
        """
        pixmap = self._video_widget.grab()
        if pixmap.isNull():
            return None
        target = Path(self._snapshot_dir) / f"capture_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not pixmap.save(str(target), "PNG"):
                return None
        except OSError:
            return None
        return target
