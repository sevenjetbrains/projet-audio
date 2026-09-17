"""Fenêtre principale d'AudioCut Studio."""

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME
from app.config.settings import FFmpegBinaries
from app.services.export_service import ExportError, merge_sequences
from app.ui.export_dialog import ExportDialog
from app.ui.sequence_list import SequenceListWidget
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
        self._sequence_list = SequenceListWidget(self._video_panel.ffmpeg_service)

        self._selection_start_spin = QDoubleSpinBox()
        self._selection_end_spin = QDoubleSpinBox()
        for spin in (self._selection_start_spin, self._selection_end_spin):
            spin.setDecimals(3)
            spin.setSuffix(" s")
            spin.setRange(0.0, 0.0)

        self._create_sequence_button = QPushButton("Créer une séquence")
        self._create_sequence_button.clicked.connect(self._on_create_sequence_clicked)

        selection_form = QFormLayout()
        selection_form.addRow("Début :", self._selection_start_spin)
        selection_form.addRow("Fin :", self._selection_end_spin)
        selection_form.addRow(self._create_sequence_button)

        self._merge_preview_button = QPushButton("Fusionner et prévisualiser")
        self._merge_preview_button.clicked.connect(self._on_merge_preview_clicked)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self._transport_controls, stretch=1)
        bottom_layout.addWidget(self._merge_preview_button)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self._video_panel)
        layout.addWidget(self._waveform_widget, stretch=1)
        layout.addLayout(selection_form)
        layout.addWidget(self._sequence_list, stretch=1)
        layout.addLayout(bottom_layout)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._build_menu()
        self._wire_signals()

    def _build_menu(self) -> None:
        export_action = QAction("Exporter…", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_clicked)

        menu = self.menuBar().addMenu("Export")
        menu.addAction(export_action)

    def _wire_signals(self) -> None:
        self._video_panel.audio_ready.connect(self._on_audio_ready)
        self._waveform_widget.seek_requested.connect(self._transport_controls.set_position_seconds)
        self._transport_controls.position_changed.connect(self._waveform_widget.set_playhead)
        self._waveform_widget.selection_changed.connect(self._on_selection_changed)
        self._selection_start_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._selection_end_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._sequence_list.play_requested.connect(self._on_sequence_play_requested)

    def _on_audio_ready(self, wav_path: str, duration: float) -> None:
        self._waveform_widget.load(wav_path, duration)
        self._transport_controls.set_source(wav_path)
        self._sequence_list.set_project(self._video_panel.project)

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

    def _on_create_sequence_clicked(self) -> None:
        start = self._selection_start_spin.value()
        end = self._selection_end_spin.value()
        if end <= start:
            QMessageBox.warning(self, "AudioCut Studio", "Sélectionnez une plage valide avant de créer une séquence.")
            return
        self._sequence_list.add_sequence_from_selection(start, end)

    def _on_sequence_play_requested(self, name: str, audio_path: str) -> None:
        self._transport_controls.set_source(audio_path)

    def _on_merge_preview_clicked(self) -> None:
        project = self._video_panel.project
        if project is None:
            return
        try:
            final_wav = merge_sequences(project, self._video_panel.ffmpeg_service)
        except ExportError as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return
        self._transport_controls.set_source(final_wav)

    def _on_export_clicked(self) -> None:
        project = self._video_panel.project
        if project is None or not project.sequences:
            QMessageBox.warning(self, "AudioCut Studio", "Créez au moins une séquence avant d'exporter.")
            return
        dialog = ExportDialog(project, self._video_panel.ffmpeg_service, self)
        dialog.exec()
