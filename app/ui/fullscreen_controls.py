"""Barre de contrôle affichée par-dessus la vidéo en plein écran : lecture/pause, progression, temps.

Le widget ne connaît pas le lecteur : il reçoit la position, la durée et l'état de lecture, et émet des
demandes (bascule lecture/pause, déplacement, saut). La fenêtre plein écran l'affiche et le masque ;
`VideoPlayerPanel` le relie aux contrôles de transport.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QStyle, QWidget

from app.ui.icons import ICON_SIZE, render_icon
from app.utils.time_utils import format_timecode_fr

_ICON_COLOR = "#ffffff"  # la barre est toujours sombre, quel que soit le thème de l'application
_STYLE = """
FullscreenControls {
    background-color: rgba(0, 0, 0, 175);
}
FullscreenControls QLabel {
    color: #ffffff;
    font-size: 14px;
    background: transparent;
}
FullscreenControls QPushButton {
    background: transparent;
    border: none;
    border-radius: 6px;
}
FullscreenControls QPushButton:hover {
    background-color: rgba(255, 255, 255, 40);
}
FullscreenControls QSlider::groove:horizontal {
    height: 6px;
    background: rgba(255, 255, 255, 70);
    border-radius: 3px;
}
FullscreenControls QSlider::sub-page:horizontal {
    background: #e2622c;
    border-radius: 3px;
}
FullscreenControls QSlider::handle:horizontal {
    width: 16px;
    margin: -5px 0;
    background: #ffffff;
    border-radius: 8px;
}
"""


class _SeekSlider(QSlider):
    """Curseur dont un clic dans la rainure saute directement à l'endroit cliqué (et non d'une page)."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), max(self.width(), 1)
            )
            self.setValue(value)  # saut immédiat ; le glissement qui suit est géré par le clic normal ci-dessous
        super().mousePressEvent(event)


class FullscreenControls(QWidget):
    play_toggled = Signal()
    seek_live = Signal(float)  # pendant un glissement : déplacements à regrouper
    seek_committed = Signal(float)  # au relâchement : position exacte
    skip_requested = Signal(float)  # ±N secondes (flèches du clavier)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self._duration = 0.0
        self._dragging = False
        self._playing = False

        self._play_button = QPushButton()
        self._play_button.setFixedSize(44, 44)
        self._play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._play_button.setToolTip("Lecture / pause (Espace)")
        self._play_button.clicked.connect(self.play_toggled.emit)
        self._show_icon("play")

        self._slider = _SeekSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # les touches restent gérées par la fenêtre
        self._slider.sliderPressed.connect(self._on_press)
        self._slider.sliderReleased.connect(self._on_release)
        self._slider.valueChanged.connect(self._on_value_changed)

        self._position_label = QLabel(format_timecode_fr(0.0))
        self._duration_label = QLabel(format_timecode_fr(0.0))
        self._position_label.setMinimumWidth(110)
        self._duration_label.setMinimumWidth(110)
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(14)
        layout.addWidget(self._play_button)
        layout.addWidget(self._position_label)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._duration_label)

    # --- État reçu du lecteur -----------------------------------------------------------------------

    def set_duration(self, seconds: float) -> None:
        self._duration = max(seconds, 0.0)
        self._duration_label.setText(format_timecode_fr(self._duration))
        self._slider.blockSignals(True)
        self._slider.setRange(0, int(self._duration * 1000))
        self._slider.blockSignals(False)

    def set_position(self, seconds: float, duration: float | None = None) -> None:
        """Position de lecture (et, si elle a changé, durée du média en cours)."""
        if duration is not None and abs(duration - self._duration) > 0.001:
            self.set_duration(duration)
        self._position_label.setText(format_timecode_fr(seconds))
        if self._dragging:
            return  # l'utilisateur tient le curseur : la lecture ne doit pas le tirer en arrière
        self._slider.blockSignals(True)
        self._slider.setValue(int(seconds * 1000))
        self._slider.blockSignals(False)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._show_icon("pause" if playing else "play")
        self._play_button.setToolTip(("Pause" if playing else "Lecture") + " (Espace)")

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    # --- Interactions -------------------------------------------------------------------------------

    def _show_icon(self, name: str) -> None:
        self._play_button.setIcon(QIcon(render_icon(name, _ICON_COLOR, size=ICON_SIZE)))
        self._play_button.setIconSize(QSize(ICON_SIZE + 6, ICON_SIZE + 6))

    def _on_press(self) -> None:
        self._dragging = True

    def _on_release(self) -> None:
        self._dragging = False
        seconds = self._slider.value() / 1000.0
        self._position_label.setText(format_timecode_fr(seconds))
        self.seek_committed.emit(seconds)

    def _on_value_changed(self, value: int) -> None:
        seconds = value / 1000.0
        self._position_label.setText(format_timecode_fr(seconds))
        if self._dragging:
            self.seek_live.emit(seconds)
        else:
            self.seek_committed.emit(seconds)  # pas de glissement (ex. touches du curseur) : déplacement direct
