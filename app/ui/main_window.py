"""Fenêtre principale d'AudioCut Studio."""

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QMainWindow, QVBoxLayout, QWidget

from app.config.constants import APP_NAME
from app.config.settings import FFmpegBinaries
from app.ui.transport_controls import TransportControls
from app.ui.video_panel import VideoPanel
from app.ui.waveform_widget import WaveformWidget


class MainWindow(QMainWindow):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        self._video_panel = VideoPanel(ffmpeg_binaries)
        self._waveform_widget = WaveformWidget()
        self._transport_controls = TransportControls()

        self._selection_start_spin = QDoubleSpinBox()
        self._selection_end_spin = QDoubleSpinBox()
        for spin in (self._selection_start_spin, self._selection_end_spin):
            spin.setDecimals(3)
            spin.setSuffix(" s")
            spin.setRange(0.0, 0.0)

        selection_form = QFormLayout()
        selection_form.addRow("Début :", self._selection_start_spin)
        selection_form.addRow("Fin :", self._selection_end_spin)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self._video_panel)
        layout.addWidget(self._waveform_widget, stretch=1)
        layout.addLayout(selection_form)
        layout.addWidget(self._transport_controls)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._wire_signals()

    def _wire_signals(self) -> None:
        self._video_panel.audio_ready.connect(self._on_audio_ready)
        self._waveform_widget.seek_requested.connect(self._transport_controls.set_position_seconds)
        self._transport_controls.position_changed.connect(self._waveform_widget.set_playhead)
        self._waveform_widget.selection_changed.connect(self._on_selection_changed)
        self._selection_start_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._selection_end_spin.valueChanged.connect(self._on_selection_spin_changed)

    def _on_audio_ready(self, wav_path: str, duration: float) -> None:
        self._waveform_widget.load(wav_path, duration)
        self._transport_controls.set_source(wav_path)

        for spin in (self._selection_start_spin, self._selection_end_spin):
            spin.blockSignals(True)
            spin.setRange(0.0, duration)
            spin.blockSignals(False)
        self._selection_start_spin.setValue(0.0)
        self._selection_end_spin.setValue(0.0)

    def _on_selection_changed(self, start: float, end: float) -> None:
        self._selection_start_spin.blockSignals(True)
        self._selection_end_spin.blockSignals(True)
        self._selection_start_spin.setValue(start)
        self._selection_end_spin.setValue(end)
        self._selection_start_spin.blockSignals(False)
        self._selection_end_spin.blockSignals(False)

    def _on_selection_spin_changed(self) -> None:
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        self._waveform_widget.set_selection(start, end)
