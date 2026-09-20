"""Aperçu vidéo : QVideoWidget, avec un message d'attente tant qu'aucune vidéo n'est chargée."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QStackedLayout, QVBoxLayout, QWidget

from app.config.settings import TEMP_DIR
from app.ui.fullscreen_controls import FullscreenControls

_PLACEHOLDER = "▶\nimage de la vidéo"
_CONTROLS_IDLE_MS = 2500  # sans mouvement de souris, la barre de contrôle se masque
_KEY_SKIP_SECONDS = 5.0


class _FullscreenWindow(QWidget):
    """Fenêtre plein écran noire qui accueille temporairement l'image vidéo et sa barre de contrôle.

    Échap, un double-clic ou la fermeture de la fenêtre demandent le retour (`exit_requested`) : c'est
    `VideoPreview` qui remet ensuite l'image à sa place, pour que la fenêtre ne se ferme jamais avec elle.
    La barre de contrôle se superpose en bas de l'image et se masque après un moment sans mouvement de souris.
    """

    exit_requested = Signal()

    def __init__(self, controls: FullscreenControls, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Aperçu vidéo")
        self.setStyleSheet("background-color: black;")
        self.setMouseTracking(True)
        self._controls = controls
        controls.setParent(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(_CONTROLS_IDLE_MS)
        self._idle_timer.timeout.connect(self._hide_controls)

    def attach_video(self, video_widget: QWidget) -> None:
        """Place l'image dans la fenêtre ; ses mouvements de souris réveillent la barre de contrôle."""
        self.layout().addWidget(video_widget)
        video_widget.setMouseTracking(True)
        video_widget.installEventFilter(self)
        self._show_controls()

    def release_video(self, video_widget: QWidget) -> None:
        video_widget.removeEventFilter(self)
        self.layout().removeWidget(video_widget)

    # --- Barre de contrôle : placement et masquage automatique --------------------------------------

    def _place_controls(self) -> None:
        height = self._controls.sizeHint().height()
        self._controls.setGeometry(0, self.height() - height, self.width(), height)
        self._controls.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_controls()

    def _show_controls(self) -> None:
        self.unsetCursor()
        self._place_controls()
        self._controls.show()
        self._controls.raise_()
        self._idle_timer.start()

    def _hide_controls(self) -> None:
        # On garde la barre à l'écran tant qu'on la manipule ou que la lecture est en pause.
        if self._controls.is_dragging or not self._controls.is_playing or self._controls.underMouse():
            self._idle_timer.start()
            return
        self._controls.hide()
        self.setCursor(Qt.CursorShape.BlankCursor)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress):
            self._show_controls()
        return False

    def mouseMoveEvent(self, event) -> None:
        self._show_controls()
        super().mouseMoveEvent(event)

    # --- Clavier et fermeture -----------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # Traitées ici plutôt que par des raccourcis : elles marchent même si Qt ne juge pas la fenêtre « active ».
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.exit_requested.emit()
        elif key == Qt.Key.Key_Space:
            self._controls.play_toggled.emit()
            self._show_controls()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self._controls.skip_requested.emit(-_KEY_SKIP_SECONDS if key == Qt.Key.Key_Left else _KEY_SKIP_SECONDS)
            self._show_controls()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.exit_requested.emit()

    def closeEvent(self, event) -> None:
        event.ignore()  # la fermeture passe par VideoPreview, qui rend d'abord l'image à l'application
        self.exit_requested.emit()


class VideoPreview(QWidget):
    """Sortie vidéo du lecteur : permet de visualiser la vidéo pour repérer les passages à extraire."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self._snapshot_dir = TEMP_DIR
        self._fullscreen_window: _FullscreenWindow | None = None
        # Créée une fois, reliée au lecteur par VideoPlayerPanel ; posée dans la fenêtre plein écran quand il y en a une.
        self._fullscreen_controls = FullscreenControls(self)
        self._fullscreen_controls.hide()

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
        """Vrai quand l'image vidéo est affichée, y compris en plein écran (où elle a quitté la mise en page)."""
        return self.is_fullscreen or self._stack.currentWidget() is self._video_widget

    def set_active(self, active: bool) -> None:
        """Bascule entre l'image vidéo et le message d'attente."""
        if self.is_fullscreen:
            if active:
                return  # l'image est déjà affichée, en plein écran
            self._leave_fullscreen()  # plus d'image à montrer : on rend la main à l'application
        self._stack.setCurrentWidget(self._video_widget if active else self._placeholder)

    def set_snapshot_dir(self, directory: str) -> None:
        """Dossier où écrire les captures d'image (le dossier temporaire du projet ouvert)."""
        if directory:
            self._snapshot_dir = Path(directory)

    @property
    def fullscreen_controls(self) -> FullscreenControls:
        return self._fullscreen_controls

    @property
    def is_fullscreen(self) -> bool:
        return self._fullscreen_window is not None

    def toggle_fullscreen(self) -> None:
        """Passe l'image vidéo en plein écran, ou en revient (Échap ou double-clic dans le plein écran).

        Le plein écran natif de QVideoWidget, lui, détachait l'image en une petite fenêtre noire dans le coin
        de l'écran quand le widget vit dans une mise en page : on déplace donc l'image dans une vraie fenêtre
        plein écran, puis on la remet exactement à sa place.
        """
        if self.is_fullscreen:
            self._leave_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        if not self.is_active:
            return  # rien à afficher : le message d'attente n'a pas à être mis en plein écran
        window = _FullscreenWindow(self._fullscreen_controls, self.window())
        window.exit_requested.connect(self._leave_fullscreen)
        self._fullscreen_window = window

        self._stack.removeWidget(self._video_widget)
        window.attach_video(self._video_widget)
        self._video_widget.show()
        window.setScreen(self.screen())  # l'écran où se trouve l'application, pas forcément l'écran principal
        window.showFullScreen()
        window.activateWindow()
        window.setFocus()

    def _leave_fullscreen(self) -> None:
        window = self._fullscreen_window
        if window is None:
            return
        self._fullscreen_window = None
        window.release_video(self._video_widget)
        self._fullscreen_controls.hide()
        self._fullscreen_controls.setParent(self)  # évite qu'elle soit détruite avec la fenêtre plein écran
        self._stack.addWidget(self._video_widget)
        self._stack.setCurrentWidget(self._video_widget)
        self._video_widget.show()
        window.hide()
        window.deleteLater()

    def closeEvent(self, event) -> None:
        # Le plein écran est une fenêtre à part : elle ne doit jamais survivre à l'aperçu qui l'a ouverte.
        if self.is_fullscreen:
            self._leave_fullscreen()
        super().closeEvent(event)

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
