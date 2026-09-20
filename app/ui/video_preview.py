"""Aperçu vidéo : QVideoWidget, avec un message d'attente tant qu'aucune vidéo n'est chargée."""

from PySide6.QtCore import Qt
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QStackedLayout, QWidget


class VideoPreview(QWidget):
    """Sortie vidéo du lecteur : permet de visualiser la vidéo pour repérer les passages à extraire."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 180)

        self._video_widget = QVideoWidget()
        self._placeholder = QLabel("Aucune vidéo importée.")
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
