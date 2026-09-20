"""Contrôles de lecture (Play/Pause, position) encapsulant QMediaPlayer/QAudioOutput."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QSlider, QWidget

from app.ui.design import icon_button, label
from app.ui.shortcuts import set_button_shortcut
from app.utils.time_utils import format_timecode

_SKIP_SECONDS = 5.0
_PLAY_GLYPH = "▶"
_PAUSE_GLYPH = "⏸"
_DEFAULT_VOLUME = 78


class TransportControls(QWidget):
    position_changed = Signal(float)
    playback_error = Signal(str)
    playing_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.errorOccurred.connect(self._on_error_occurred)

        self._play_button = icon_button(_PLAY_GLYPH, size=40)
        self._play_button.setProperty("accent", "true")
        self._play_button.clicked.connect(self._toggle_play_pause)
        self._play_button.setEnabled(False)
        self._play_button.setToolTip("Lecture / pause (Espace)")

        self._stop_button = icon_button("■")
        self._stop_button.clicked.connect(self.stop)
        self._stop_button.setEnabled(False)
        set_button_shortcut(self._stop_button, "Ctrl+Space", "Arrêter la lecture")

        self._back_button = icon_button("≪")
        self._back_button.clicked.connect(lambda: self.skip(-_SKIP_SECONDS))
        self._back_button.setEnabled(False)
        set_button_shortcut(self._back_button, "Alt+Left", f"Reculer de {_SKIP_SECONDS:.0f} s")

        self._forward_button = icon_button("≫")
        self._forward_button.clicked.connect(lambda: self.skip(_SKIP_SECONDS))
        self._forward_button.setEnabled(False)
        set_button_shortcut(self._forward_button, "Alt+Right", f"Avancer de {_SKIP_SECONDS:.0f} s")

        self._now_playing_label = label("", "mutedLabel")
        self._position_label = label("00:00:00.000 / 00:00:00.000", "valueLabel")
        self._position_label.hide()  # le timecode de référence est affiché au-dessus de la waveform

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(_DEFAULT_VOLUME)
        self._volume_slider.setFixedWidth(96)
        self._volume_slider.setToolTip("Volume")
        self._volume_slider.valueChanged.connect(self.set_volume_percent)
        self._volume_label = label(f"{_DEFAULT_VOLUME} %", "mutedLabel")
        self._volume_label.setFixedWidth(38)
        self._volume_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.set_volume_percent(_DEFAULT_VOLUME)

        self.setLayout(self._build_layout())

        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        shortcut.activated.connect(self._toggle_play_pause)

    def _build_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(self._back_button)
        layout.addWidget(self._play_button)
        layout.addWidget(self._stop_button)
        layout.addWidget(self._forward_button)
        layout.addSpacing(6)
        layout.addWidget(self._now_playing_label, 1)
        layout.addWidget(label("🔊", "mutedLabel"))
        layout.addWidget(label("Volume", "mutedLabel"))
        layout.addWidget(self._volume_slider)
        layout.addWidget(self._volume_label)
        return layout

    # --- Source et état ---------------------------------------------------

    def set_source(self, wav_path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(wav_path))
        for button in (self._play_button, self._stop_button, self._back_button, self._forward_button):
            button.setEnabled(True)

    def set_video_output(self, video_widget) -> None:
        """Branche la sortie vidéo du lecteur (aperçu de la vidéo source)."""
        self._player.setVideoOutput(video_widget)

    def set_now_playing(self, name: str) -> None:
        """Nom du média en cours affiché dans la barre (séquence, source, aperçu fusionné)."""
        self._now_playing_label.setText(name)

    @property
    def position_seconds(self) -> float:
        return self._player.position() / 1000.0

    @property
    def duration_seconds(self) -> float:
        return max(self._player.duration(), 0) / 1000.0

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    # --- Commandes --------------------------------------------------------

    def play(self) -> None:
        if self._play_button.isEnabled():
            self._player.play()

    def load_and_play(self, wav_path: str) -> None:
        """Charge le fichier puis lance directement la lecture."""
        self.set_source(wav_path)
        self._player.play()

    def stop(self) -> None:
        self._player.stop()

    def skip(self, delta_seconds: float) -> None:
        """Avance ou recule la lecture, bornée à [0, durée]."""
        target = self._player.position() + int(delta_seconds * 1000)
        duration = self._player.duration()
        if duration > 0:
            target = min(target, duration)
        self._player.setPosition(max(0, target))

    def set_volume_percent(self, percent: int) -> None:
        bounded = max(0, min(100, percent))
        self._audio_output.setVolume(bounded / 100.0)
        self._volume_label.setText(f"{bounded} %")

    def set_muted(self, muted: bool) -> None:
        self._audio_output.setMuted(muted)

    @property
    def is_muted(self) -> bool:
        return self._audio_output.isMuted()

    def set_playback_rate(self, rate: float) -> None:
        self._player.setPlaybackRate(rate)

    def set_position_seconds(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))

    def toggle_play_pause(self) -> None:
        """Bascule lecture/pause (barre de transport, touche Espace, bouton du lecteur vidéo)."""
        if not self._play_button.isEnabled():
            return
        if self.is_playing:
            self._player.pause()
        else:
            self._player.play()

    # Conservé comme point d'entrée interne historique des connexions de signaux.
    _toggle_play_pause = toggle_play_pause

    # --- Réactions du lecteur ---------------------------------------------

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_button.setText(_PAUSE_GLYPH if playing else _PLAY_GLYPH)
        self._play_button.setToolTip(("Pause" if playing else "Lecture") + " (Espace)")
        self.playing_changed.emit(playing)

    def _on_error_occurred(self, _error, error_string: str) -> None:
        """Média illisible (codec non géré par Qt, fichier absent) : l'appelant peut proposer un repli."""
        self.playback_error.emit(error_string)

    def _on_position_changed(self, position_ms: int) -> None:
        seconds = position_ms / 1000.0
        self._position_label.setText(f"{format_timecode(seconds)} / {format_timecode(self.duration_seconds)}")
        self.position_changed.emit(seconds)
