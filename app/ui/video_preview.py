"""Aperçu vidéo : QVideoWidget, avec un message d'attente tant qu'aucune vidéo n'est chargée."""

from datetime import datetime
from pathlib import Path

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QLabel, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget

from app.config.settings import TEMP_DIR
from app.ui.fullscreen_controls import FullscreenControls

_PLACEHOLDER = "▶\nimage de la vidéo"
_CONTROLS_IDLE_MS = 2500  # sans mouvement de souris, la barre de contrôle se masque
_KEY_SKIP_SECONDS = 5.0
_DEFAULT_ASPECT = 16 / 9
_MIN_WIDTH, _MIN_HEIGHT = 320, 180
_MAX_HEIGHT = 420  # une vidéo verticale ne doit pas rendre le panneau démesurément haut
_CURSOR_POLL_MS = 100  # fréquence de détection d'un mouvement de souris (voir _FullscreenWindow._poll_cursor)


class _FullscreenWindow(QWidget):
    """Fenêtre plein écran noire qui accueille temporairement l'image vidéo et sa barre de contrôle.

    Échap, un double-clic ou la fermeture de la fenêtre demandent le retour (`exit_requested`) : c'est
    `VideoPreview` qui remet ensuite l'image à sa place, pour que la fenêtre ne se ferme jamais avec elle.
    La barre de contrôle se superpose en bas de l'image et se masque après un moment sans mouvement de souris.

    Dans Qt 6, l'image vidéo est une fenêtre native : elle recouvre toujours les widgets voisins, qui restent
    invisibles derrière elle. La barre est donc une fenêtre à part (sans bordure, sans prise de focus),
    rattachée à cette fenêtre et posée par-dessus, et non un widget enfant. Pour la même raison, les mouvements de
    souris au-dessus de l'image n'arrivent pas jusqu'ici : on surveille la position du curseur à intervalles réguliers.
    """

    exit_requested = Signal()

    def __init__(self, controls: FullscreenControls, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("Aperçu vidéo")
        # Limité à cette fenêtre : sans sélecteur, le noir serait hérité par la barre de contrôle et ses widgets.
        self.setObjectName("fullscreenVideoWindow")
        self.setStyleSheet("#fullscreenVideoWindow { background-color: black; }")
        self.setMouseTracking(True)
        self._controls = controls
        controls.setParent(self, FullscreenControls.OVERLAY_FLAGS)
        controls.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        controls.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(_CONTROLS_IDLE_MS)
        self._idle_timer.timeout.connect(self._hide_controls)

        self._last_cursor = QCursor.pos()
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(_CURSOR_POLL_MS)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._cursor_timer.start()

    def attach_video(self, video_widget: QWidget) -> None:
        """Place l'image dans la fenêtre ; ses mouvements de souris réveillent la barre de contrôle."""
        self.layout().addWidget(video_widget)
        self._show_controls()

    def release_video(self, video_widget: QWidget) -> None:
        self.layout().removeWidget(video_widget)

    # --- Barre de contrôle : placement et masquage automatique --------------------------------------

    def _place_controls(self) -> None:
        """Colle la barre au bord bas de l'écran (coordonnées globales : c'est une fenêtre à part entière)."""
        height = self._controls.sizeHint().height()
        top_left = self.mapToGlobal(QPoint(0, self.height() - height))
        self._controls.setGeometry(QRect(top_left, QSize(self.width(), height)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_controls()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._place_controls()

    def showEvent(self, event) -> None:
        super().showEvent(event)
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

    def _poll_cursor(self) -> None:
        """Réveille la barre quand le curseur a bougé (les événements souris de l'image native n'arrivent pas ici)."""
        position = QCursor.pos()
        if position != self._last_cursor:
            self._last_cursor = position
            self._show_controls()

    def mouseMoveEvent(self, event) -> None:
        self._show_controls()
        super().mouseMoveEvent(event)

    # --- Clavier et fermeture -----------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        # Traitées ici plutôt que par des raccourcis : elles marchent même si Qt ne juge pas la fenêtre « active ».
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_F, Qt.Key.Key_F11):
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


class _AspectStackedLayout(QStackedLayout):
    """Pile dont la hauteur découle de la largeur et du format de la vidéo (largeur ÷ format).

    Sans cela, la taille demandée au reste de la fenêtre était la taille naturelle du lecteur vidéo (celle de la
    vidéo, 640×360…), qui n'entrait en jeu qu'à certains moments : après un passage en plein écran, l'aperçu doublait
    de hauteur et ne revenait jamais à sa taille de départ. Ici la taille ne dépend que de la largeur disponible.
    """

    def __init__(self, aspect: Callable[[], float]) -> None:
        super().__init__()
        self._aspect = aspect

    def _height_for(self, width: int) -> int:
        return min(max(round(width / self._aspect()), _MIN_HEIGHT), _MAX_HEIGHT)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._height_for(width)

    def sizeHint(self) -> QSize:
        return QSize(_MIN_WIDTH, self._height_for(_MIN_WIDTH))

    def minimumSize(self) -> QSize:
        return QSize(_MIN_WIDTH, _MIN_HEIGHT)


class _ClickableVideoWidget(QVideoWidget):
    """QVideoWidget qui émet `clicked` sur un clic gauche (lecture / pause au clic sur l'image).

    Dans Qt 6, la surface vidéo peut être une fenêtre native (accélération matérielle) : un widget
    posé à côté ou par-dessus ne reçoit pas ses événements (voir `_FullscreenWindow` plus haut, où la
    barre de contrôle doit devenir une fenêtre à part et surveiller le curseur par sondage). Le clic
    est donc intercepté ici, sur le widget lui-même — son propre `mousePressEvent` reste fiable, seuls
    les événements *venus de l'extérieur* (filtres, widgets voisins) sont perdus.
    """

    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class VideoPreview(QWidget):
    """Sortie vidéo du lecteur : permet de visualiser la vidéo pour repérer les passages à extraire."""

    video_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._aspect = _DEFAULT_ASPECT
        self._snapshot_dir = TEMP_DIR
        self._fullscreen_window: _FullscreenWindow | None = None
        # Créée une fois, reliée au lecteur par VideoPlayerPanel ; posée dans la fenêtre plein écran quand il y en a une.
        self._fullscreen_controls = FullscreenControls(self)
        self._fullscreen_controls.hide()

        self._video_widget = _ClickableVideoWidget()
        self._video_widget.clicked.connect(self.video_clicked)
        # Sa taille naturelle (celle de la vidéo) ne doit jamais dicter celle de l'aperçu : voir _AspectStackedLayout.
        self._video_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._placeholder = QLabel(_PLACEHOLDER)
        self._placeholder.setObjectName("hintLabel")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._stack = _AspectStackedLayout(lambda: self._aspect)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._video_widget)
        self.setLayout(self._stack)

    def set_aspect_ratio(self, width: int, height: int) -> None:
        """Format de la vidéo affichée (largeur, hauteur en pixels) ; 16:9 si inconnu."""
        self._aspect = width / height if width > 0 and height > 0 else _DEFAULT_ASPECT
        self._stack.invalidate()
        self.updateGeometry()

    @property
    def aspect_ratio(self) -> float:
        return self._aspect

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
        # Redevient un simple widget de l'aperçu (évite qu'elle soit détruite avec la fenêtre plein écran).
        self._fullscreen_controls.setParent(self, Qt.WindowType.Widget)
        self._fullscreen_controls.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
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
