"""Lecteur vidéo de la colonne gauche : aperçu, barre de position, contrôles et vitesse.

Ce panneau ne possède pas de lecteur : il pilote le QMediaPlayer de
`TransportControls`, pour que l'image, le son et la tête de lecture de la
waveform restent une seule et même lecture.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ui.design import badge, card, icon_button, label, section_header
from app.ui.icons import set_button_icon
from app.ui.transport_controls import TransportControls
from app.ui.video_preview import VideoPreview
from app.utils.time_utils import format_timecode_fr

_PLAYBACK_RATES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
_DEFAULT_RATE_INDEX = 2
_HINT = (
    "L'image suit la waveform : déplacez la tête de lecture ou cliquez une "
    "séquence pour vous y rendre."
)


class VideoPlayerPanel(QWidget):
    """Section « LECTEUR VIDÉO » de la maquette, branchée sur les contrôles de transport."""

    snapshot_saved = Signal(str)

    def __init__(self, transport: TransportControls, preview: VideoPreview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._transport = transport
        self._preview = preview
        self._duration = 0.0
        self._scrubbing = False

        self._sync_badge = badge("synchronisé", "success")
        self._format_badge = badge("—", "neutral")
        self._sequence_badge = badge("source", "accent")

        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.setToolTip("Position de lecture")
        self._position_slider.sliderPressed.connect(self._on_scrub_started)
        self._position_slider.sliderReleased.connect(self._on_scrub_finished)
        self._position_slider.valueChanged.connect(self._on_slider_value_changed)

        self._position_label = label(format_timecode_fr(0.0), "valueLabel")
        self._duration_label = label(format_timecode_fr(0.0), "valueLabel")

        self._play_button = icon_button("play")
        self._play_button.clicked.connect(transport.toggle_play_pause)
        self._play_button.setToolTip("Lecture / pause (Espace)")
        self._mute_button = icon_button("volume")
        self._mute_button.clicked.connect(self._toggle_mute)
        self._mute_button.setToolTip("Couper / rétablir le son")
        self._snapshot_button = icon_button("camera")
        self._snapshot_button.clicked.connect(self._save_snapshot)
        self._snapshot_button.setToolTip("Enregistrer l'image affichée en PNG")
        self._fullscreen_button = icon_button("fullscreen")
        self._fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self._fullscreen_button.setToolTip("Afficher l'aperçu en plein écran")

        self._rate_combo = QComboBox()
        for rate in _PLAYBACK_RATES:
            self._rate_combo.addItem(f"{rate:g} ×".replace(".", ","), rate)
        self._rate_combo.setCurrentIndex(_DEFAULT_RATE_INDEX)
        self._rate_combo.setToolTip("Vitesse de lecture")
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)

        self.setLayout(self._build_layout())

        transport.position_changed.connect(self._on_position_changed)
        transport.playing_changed.connect(self._on_playing_changed)
        self._wire_fullscreen_controls()

    def _wire_fullscreen_controls(self) -> None:
        """Relie la barre du plein écran au lecteur : elle affiche sa position et lui envoie ses commandes."""
        controls = self._preview.fullscreen_controls
        transport = self._transport
        transport.position_changed.connect(lambda seconds: controls.set_position(seconds, transport.duration_seconds))
        transport.playing_changed.connect(controls.set_playing)
        controls.play_toggled.connect(transport.toggle_play_pause)
        controls.seek_live.connect(transport.seek_throttled)
        controls.seek_committed.connect(transport.set_position_seconds)
        controls.skip_requested.connect(transport.skip)
        controls.set_playing(transport.is_playing)

    # --- Construction de l'interface --------------------------------------

    def _build_layout(self) -> QVBoxLayout:
        badges = QHBoxLayout()
        badges.setContentsMargins(10, 10, 10, 0)
        badges.addWidget(self._format_badge)
        badges.addStretch(1)
        badges.addWidget(self._sequence_badge)

        stage = card()
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        stage_layout.addLayout(badges)
        stage_layout.addWidget(self._preview, 1)

        timecodes = QHBoxLayout()
        timecodes.setContentsMargins(0, 0, 0, 0)
        timecodes.addWidget(self._position_label)
        timecodes.addStretch(1)
        timecodes.addWidget(self._duration_label)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self._play_button)
        controls.addWidget(self._mute_button)
        controls.addWidget(self._snapshot_button)
        controls.addWidget(self._fullscreen_button)
        controls.addStretch(1)
        controls.addWidget(self._rate_combo)

        hint = label(_HINT, "hintLabel")
        hint.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        layout.addWidget(section_header("Lecteur vidéo", self._sync_badge))
        layout.addWidget(stage)
        layout.addWidget(self._position_slider)
        layout.addLayout(timecodes)
        layout.addLayout(controls)
        layout.addWidget(hint)
        return layout

    # --- API publique ------------------------------------------------------

    def set_media_info(self, media_info) -> None:
        """Renseigne la vignette de format affichée sur l'image (résolution de la source)."""
        if media_info is None or not media_info.resolution:
            self._format_badge.setText("—")
            return
        width, height = media_info.resolution
        self._format_badge.setText(f"{width} × {height}")

    def set_now_playing(self, name: str) -> None:
        """Vignette indiquant ce que l'aperçu montre : « source » ou le nom d'une séquence."""
        self._sequence_badge.setText(name or "source")

    def set_duration(self, seconds: float) -> None:
        self._duration = max(seconds, 0.0)
        self._duration_label.setText(format_timecode_fr(self._duration))
        self._position_slider.blockSignals(True)
        self._position_slider.setRange(0, int(self._duration * 1000))
        self._position_slider.blockSignals(False)

    def set_synchronised(self, synchronised: bool) -> None:
        """Indique si l'image vidéo suit la lecture, ou si seul l'audio extrait est lu."""
        self._sync_badge.setText("synchronisé" if synchronised else "audio seul")

    # --- Réactions ---------------------------------------------------------

    def _on_position_changed(self, seconds: float) -> None:
        self._position_label.setText(format_timecode_fr(seconds))
        if self._scrubbing:
            return
        self._position_slider.blockSignals(True)
        self._position_slider.setValue(int(seconds * 1000))
        self._position_slider.blockSignals(False)

    def _on_playing_changed(self, playing: bool) -> None:
        set_button_icon(self._play_button, "pause" if playing else "play")

    def _on_scrub_started(self) -> None:
        self._scrubbing = True

    def _on_scrub_finished(self) -> None:
        self._scrubbing = False
        # Position exacte au relâchement, quel que soit le dernier déplacement regroupé pendant le glissement.
        self._transport.set_position_seconds(self._position_slider.value() / 1000.0)

    def _on_slider_value_changed(self, value: int) -> None:
        """Pendant un glissement l'image suit en direct (déplacements regroupés) ; un clic dans la rainure saute."""
        if self._scrubbing:
            self._transport.seek_throttled(value / 1000.0)
        else:
            self._transport.set_position_seconds(value / 1000.0)

    def _on_rate_changed(self, index: int) -> None:
        self._transport.set_playback_rate(self._rate_combo.itemData(index))

    def _toggle_mute(self) -> None:
        muted = not self._transport.is_muted
        self._transport.set_muted(muted)
        set_button_icon(self._mute_button, "mute" if muted else "volume")

    def toggle_fullscreen(self) -> None:
        """Plein écran de la seule image vidéo (Échap ou nouveau clic pour revenir)."""
        self._preview.toggle_fullscreen()

    def _save_snapshot(self) -> None:
        """Enregistre l'image affichée à côté du projet ; l'aperçu doit être actif."""
        if not self._preview.is_active:
            QMessageBox.information(self, "AudioCut Studio", "Aucune image vidéo à enregistrer.")
            return
        target = self._preview.save_snapshot()
        if target is None:
            QMessageBox.warning(
                self,
                "AudioCut Studio",
                "L'image n'a pas pu être enregistrée : ce backend vidéo ne permet pas de la relire.",
            )
            return
        self.snapshot_saved.emit(str(target))
