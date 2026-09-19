"""Contrôles de lecture (Play/Pause, position) encapsulant QMediaPlayer/QAudioOutput."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from app.utils.time_utils import format_timecode


_SKIP_SECONDS = 5.0


class TransportControls(QWidget):
    position_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)

        self._play_button = QPushButton("▶ Lecture")
        self._play_button.clicked.connect(self._toggle_play_pause)
        self._play_button.setEnabled(False)

        self._stop_button = QPushButton("⏹ Stop")
        self._stop_button.clicked.connect(self.stop)
        self._stop_button.setEnabled(False)

        self._back_button = QPushButton(f"⏪ {_SKIP_SECONDS:.0f} s")
        self._back_button.clicked.connect(lambda: self.skip(-_SKIP_SECONDS))
        self._back_button.setEnabled(False)

        self._forward_button = QPushButton(f"{_SKIP_SECONDS:.0f} s ⏩")
        self._forward_button.clicked.connect(lambda: self.skip(_SKIP_SECONDS))
        self._forward_button.setEnabled(False)

        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setMaximumWidth(120)
        self._volume_slider.setToolTip("Volume")
        self._volume_slider.valueChanged.connect(self.set_volume_percent)

        self._position_label = QLabel("00:00:00.000 / 00:00:00.000")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._back_button)
        layout.addWidget(self._play_button)
        layout.addWidget(self._forward_button)
        layout.addWidget(self._stop_button)
        layout.addWidget(self._position_label)
        layout.addWidget(QLabel("🔊"))
        layout.addWidget(self._volume_slider)
        layout.addStretch(1)
        self.setLayout(layout)

        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        shortcut.activated.connect(self._toggle_play_pause)

    def set_source(self, wav_path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(wav_path))
        for button in (self._play_button, self._stop_button, self._back_button, self._forward_button):
            button.setEnabled(True)

    @property
    def position_seconds(self) -> float:
        return self._player.position() / 1000.0

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
        self._audio_output.setVolume(max(0, min(100, percent)) / 100.0)

    def set_position_seconds(self, seconds: float) -> None:
        self._player.setPosition(int(seconds * 1000))

    def _toggle_play_pause(self) -> None:
        if not self._play_button.isEnabled():
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_button.setText("⏸ Pause")
        else:
            self._play_button.setText("▶ Lecture")

    def _on_position_changed(self, position_ms: int) -> None:
        seconds = position_ms / 1000.0
        duration_seconds = self._player.duration() / 1000.0
        self._position_label.setText(f"{format_timecode(seconds)} / {format_timecode(duration_seconds)}")
        self.position_changed.emit(seconds)
