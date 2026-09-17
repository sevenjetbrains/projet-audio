"""Contrôles de lecture (Play/Pause, position) encapsulant QMediaPlayer/QAudioOutput."""

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.utils.time_utils import format_timecode


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

        self._position_label = QLabel("00:00:00.000 / 00:00:00.000")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._play_button)
        layout.addWidget(self._position_label)
        layout.addStretch(1)
        self.setLayout(layout)

        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        shortcut.activated.connect(self._toggle_play_pause)

    def set_source(self, wav_path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(wav_path))
        self._play_button.setEnabled(True)

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
