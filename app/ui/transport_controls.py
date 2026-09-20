"""Contrôles de lecture (Play/Pause, position) encapsulant QMediaPlayer/QAudioOutput."""

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from app.ui.design import icon_button, label
from app.ui.icons import set_button_icon, set_label_icon
from app.ui.shortcuts import set_button_shortcut
from app.utils.time_utils import format_timecode

_SKIP_SECONDS = 5.0
_PLAY_ICON = "play"
_PAUSE_ICON = "pause"
_DEFAULT_VOLUME = 78
# Délai minimal entre deux déplacements pendant un glissement : au-delà, seul le dernier est appliqué.
_SEEK_INTERVAL_MS = 40
# Pendant la lecture d'une plage, la position est relue à cette cadence : le lecteur ne la signale que toutes
# les ~100 ms, ce qui ferait dépasser la borne de fin (et rendrait la boucle audiblement décalée).
_RANGE_POLL_MS = 15
# En dessous de cette durée une boucle ne serait qu'un grésillement : la plage est jouée une fois.
_MIN_LOOP_SECONDS = 0.1


class TransportControls(QWidget):
    position_changed = Signal(float)
    playback_error = Signal(str)
    playing_changed = Signal(bool)
    range_finished = Signal()
    range_looped = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.errorOccurred.connect(self._on_error_occurred)

        self._seek_timer = QTimer(self)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.setInterval(_SEEK_INTERVAL_MS)
        self._seek_timer.timeout.connect(self._flush_pending_seek)
        self._pending_seek_ms: int | None = None
        self._restore_slot = None
        # Lecture d'une plage (« écouter la sélection ») : arrêt automatique à la fin.
        self._range_start_ms = 0
        self._range_end_ms: int | None = None
        self._range_armed = False
        self._loop_range = False
        self._range_timer = QTimer(self)
        self._range_timer.setInterval(_RANGE_POLL_MS)
        self._range_timer.timeout.connect(lambda: self._check_range_end(self._player.position()))

        self._play_button = icon_button(_PLAY_ICON, size=40)
        self._play_button.setProperty("accent", "true")
        set_button_icon(self._play_button, _PLAY_ICON)  # relancé : l'icône du bouton d'accent est blanche
        self._play_button.clicked.connect(self._toggle_play_pause)
        self._play_button.setEnabled(False)
        self._play_button.setToolTip("Lecture / pause (Espace)")

        self._stop_button = icon_button("stop")
        self._stop_button.clicked.connect(self.stop)
        self._stop_button.setEnabled(False)
        set_button_shortcut(self._stop_button, "Ctrl+Space", "Arrêter la lecture")

        self._back_button = icon_button("back")
        self._back_button.clicked.connect(lambda: self.skip(-_SKIP_SECONDS))
        self._back_button.setEnabled(False)
        set_button_shortcut(self._back_button, "Alt+Left", f"Reculer de {_SKIP_SECONDS:.0f} s")

        self._forward_button = icon_button("forward")
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
        volume_icon = QLabel()
        set_label_icon(volume_icon, "volume")
        layout.addWidget(volume_icon)
        layout.addWidget(label("Volume", "mutedLabel"))
        layout.addWidget(self._volume_slider)
        layout.addWidget(self._volume_label)
        return layout

    # --- Source et état ---------------------------------------------------

    def set_source(self, wav_path: str) -> None:
        self._clear_range()
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

    def play_range(self, start_seconds: float, end_seconds: float) -> None:
        """Lit de `start` à `end` puis se met en pause à la fin, ou reboucle si la boucle est activée."""
        if not self._play_button.isEnabled() or end_seconds <= start_seconds:
            return
        self._pending_seek_ms = None
        self._range_start_ms = int(start_seconds * 1000)
        self._range_end_ms = int(end_seconds * 1000)
        self._range_armed = False  # armée à la première position reçue AVANT la fin (voir _check_range_end)
        self._player.setPosition(self._range_start_ms)
        self._player.play()
        self._range_timer.start()

    def set_loop(self, enabled: bool) -> None:
        """Boucle de la plage : à sa fin, la lecture reprend à son début au lieu de s'arrêter."""
        self._loop_range = enabled

    @property
    def is_looping(self) -> bool:
        return self._loop_range

    def update_range(self, start_seconds: float, end_seconds: float) -> None:
        """Change les bornes de la plage en cours de lecture (réglage fin des bornes) sans l'interrompre."""
        if self._range_end_ms is None or end_seconds <= start_seconds:
            return
        self._range_start_ms = int(start_seconds * 1000)
        self._range_end_ms = int(end_seconds * 1000)
        position = self._player.position()
        if position < self._range_start_ms or position >= self._range_end_ms:
            self._restart_range()  # la lecture était hors de la nouvelle plage : retour à son début

    def _restart_range(self) -> None:
        self._range_armed = False  # des positions périmées (après la fin) peuvent encore arriver : on les ignore
        self._player.setPosition(self._range_start_ms)

    @property
    def is_playing_range(self) -> bool:
        return self._range_end_ms is not None

    def _clear_range(self) -> None:
        self._range_end_ms = None
        self._range_armed = False
        self._range_timer.stop()

    def stop(self) -> None:
        self._clear_range()
        self._player.stop()

    def skip(self, delta_seconds: float) -> None:
        """Avance ou recule la lecture, bornée à [0, durée]."""
        self._clear_range()
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
        """Déplacement immédiat et exact (clic, relâchement du curseur) ; annule tout déplacement en attente."""
        self._pending_seek_ms = None
        self._clear_range()  # l'utilisateur reprend la main : plus d'arrêt automatique
        self._player.setPosition(int(seconds * 1000))

    def seek_throttled(self, seconds: float) -> None:
        """Déplacement pour un glissement continu : le premier est immédiat, les suivants sont regroupés.

        Chaque déplacement oblige le lecteur à redécoder depuis une image clé ; en envoyer un à chaque
        pixel du curseur les empile et l'image prend du retard. Ici seul le dernier emplacement demandé
        est appliqué, au plus une fois toutes les 40 ms.
        """
        self._clear_range()
        milliseconds = int(seconds * 1000)
        if self._seek_timer.isActive():
            self._pending_seek_ms = milliseconds
            return
        self._player.setPosition(milliseconds)
        self._seek_timer.start()

    def _flush_pending_seek(self) -> None:
        if self._pending_seek_ms is None:
            return
        milliseconds, self._pending_seek_ms = self._pending_seek_ms, None
        self._player.setPosition(milliseconds)
        self._seek_timer.start()  # laisse respirer le lecteur avant d'accepter le déplacement suivant

    def replace_source_keep_position(self, path: str) -> None:
        """Change le média en gardant la position et l'état lecture/pause (ex. bascule vers l'aperçu fluide)."""
        position = self._player.position()
        was_playing = self.is_playing
        if self._restore_slot is not None:
            self._player.mediaStatusChanged.disconnect(self._restore_slot)

        def restore(status) -> None:
            if status not in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
                return
            self._player.mediaStatusChanged.disconnect(restore)
            self._restore_slot = None
            self._player.setPosition(position)
            if was_playing:
                self._player.play()

        self._restore_slot = restore
        self._player.mediaStatusChanged.connect(restore)
        self.set_source(path)

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
        set_button_icon(self._play_button, _PAUSE_ICON if playing else _PLAY_ICON)
        self._play_button.setToolTip(("Pause" if playing else "Lecture") + " (Espace)")
        self.playing_changed.emit(playing)

    def _on_error_occurred(self, _error, error_string: str) -> None:
        """Média illisible (codec non géré par Qt, fichier absent) : l'appelant peut proposer un repli."""
        self.playback_error.emit(error_string)

    def _on_position_changed(self, position_ms: int) -> None:
        seconds = position_ms / 1000.0
        self._position_label.setText(f"{format_timecode(seconds)} / {format_timecode(self.duration_seconds)}")
        self.position_changed.emit(seconds)
        self._check_range_end(position_ms)

    def _check_range_end(self, position_ms: int) -> None:
        end = self._range_end_ms
        if end is None:
            return
        if position_ms < end:
            self._range_armed = True
            return
        if not self._range_armed:
            return  # position périmée reçue avant que le déplacement au début de la plage soit appliqué
        long_enough = (end - self._range_start_ms) / 1000.0 >= _MIN_LOOP_SECONDS
        if self._loop_range and long_enough:
            self._restart_range()
            self.range_looped.emit()
            return
        self._clear_range()
        self._player.pause()
        self._player.setPosition(end)
        self.range_finished.emit()
