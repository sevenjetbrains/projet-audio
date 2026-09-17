"""Fenêtre principale d'AudioCut Studio."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME
from app.config.settings import FFmpegBinaries
from app.services.export_service import ExportError, merge_sequences
from app.services.project_service import PROJECT_FILE_EXTENSION, ProjectLoadError, load_project, save_project
from app.ui.audio_processing_panel import AudioProcessingPanel
from app.ui.export_dialog import ExportDialog
from app.ui.sequence_list import SequenceListWidget
from app.ui.transport_controls import TransportControls
from app.ui.video_panel import VideoPanel
from app.ui.waveform_widget import WaveformWidget
from app.workers.ffmpeg_worker import FFmpegTaskWorker


class MainWindow(QMainWindow):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)

        self._video_panel = VideoPanel(ffmpeg_binaries)
        self._waveform_widget = WaveformWidget()
        self._transport_controls = TransportControls()
        self._sequence_list = SequenceListWidget(self._video_panel.ffmpeg_service)
        self._audio_processing_panel = AudioProcessingPanel(self._video_panel.ffmpeg_service)

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

        self._crossfade_spin = QDoubleSpinBox()
        self._crossfade_spin.setRange(0.0, 5.0)
        self._crossfade_spin.setSingleStep(0.1)
        self._crossfade_spin.setSuffix(" s")
        self._crossfade_spin.setPrefix("Crossfade : ")
        self._crossfade_spin.valueChanged.connect(self._on_crossfade_changed)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self._transport_controls, stretch=1)
        bottom_layout.addWidget(self._crossfade_spin)
        bottom_layout.addWidget(self._merge_preview_button)

        middle_layout = QHBoxLayout()
        middle_layout.addWidget(self._sequence_list, stretch=1)
        middle_layout.addWidget(self._audio_processing_panel, stretch=1)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self._video_panel)
        layout.addWidget(self._waveform_widget, stretch=1)
        layout.addLayout(selection_form)
        layout.addLayout(middle_layout, stretch=1)
        layout.addLayout(bottom_layout)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._build_menu()
        self._wire_signals()

    def _build_menu(self) -> None:
        import_action = QAction("Importer une vidéo…", self)
        import_action.setShortcut(QKeySequence("Ctrl+O"))
        import_action.triggered.connect(self._video_panel.trigger_import)
        file_menu = self.menuBar().addMenu("Fichier")
        file_menu.addAction(import_action)

        save_action = QAction("Sauvegarder le projet…", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save_project_clicked)
        open_action = QAction("Ouvrir un projet…", self)
        open_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_action.triggered.connect(self._on_open_project_clicked)
        project_menu = self.menuBar().addMenu("Projet")
        project_menu.addAction(save_action)
        project_menu.addAction(open_action)

        export_action = QAction("Exporter…", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_clicked)
        export_menu = self.menuBar().addMenu("Export")
        export_menu.addAction(export_action)

    def _wire_signals(self) -> None:
        self._video_panel.audio_ready.connect(self._on_audio_ready)
        self._waveform_widget.seek_requested.connect(self._transport_controls.set_position_seconds)
        self._transport_controls.position_changed.connect(self._waveform_widget.set_playhead)
        self._waveform_widget.selection_changed.connect(self._on_selection_changed)
        self._selection_start_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._selection_end_spin.valueChanged.connect(self._on_selection_spin_changed)
        self._sequence_list.play_requested.connect(self._on_sequence_play_requested)
        self._sequence_list.sequence_selected.connect(self._on_sequence_selected)
        self._sequence_list.sequences_changed.connect(self._on_sequences_changed)
        self._audio_processing_panel.processed.connect(self._sequence_list.refresh)

    def _on_audio_ready(self, wav_path: str, duration: float) -> None:
        self._waveform_widget.load(wav_path, duration)
        self._transport_controls.set_source(wav_path)
        self._sequence_list.set_project(self._video_panel.project)
        self._audio_processing_panel.set_project(self._video_panel.project)
        self._crossfade_spin.blockSignals(True)
        self._crossfade_spin.setValue(self._video_panel.project.crossfade_duration)
        self._crossfade_spin.blockSignals(False)

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

    def _on_crossfade_changed(self, value: float) -> None:
        project = self._video_panel.project
        if project is not None:
            project.crossfade_duration = value

    def _on_sequence_play_requested(self, name: str, audio_path: str) -> None:
        self._transport_controls.set_source(audio_path)

    def _on_sequence_selected(self, sequence_id: str) -> None:
        self._audio_processing_panel.set_sequence(self._sequence_list.get_sequence(sequence_id))

    def _on_sequences_changed(self) -> None:
        self._audio_processing_panel.set_sequence(self._sequence_list.current_sequence())

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

    def _on_save_project_clicked(self) -> None:
        project = self._video_panel.project
        if project is None:
            QMessageBox.warning(self, "AudioCut Studio", "Importez une vidéo avant de sauvegarder un projet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder le projet", "", f"Projet AudioCut Studio (*{PROJECT_FILE_EXTENSION})"
        )
        if not path:
            return
        if not path.endswith(PROJECT_FILE_EXTENSION):
            path += PROJECT_FILE_EXTENSION

        save_project(project, path)
        QMessageBox.information(self, "AudioCut Studio", f"Projet sauvegardé :\n{path}")

    def _on_open_project_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet", "", f"Projet AudioCut Studio (*{PROJECT_FILE_EXTENSION})"
        )
        if not path:
            return

        progress = QProgressDialog("Chargement du projet…", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()

        self._load_worker = FFmpegTaskWorker(
            lambda: load_project(path, self._video_panel.ffprobe_service, self._video_panel.ffmpeg_service)
        )
        self._load_worker.succeeded.connect(lambda project: self._on_project_loaded(project, progress))
        self._load_worker.failed.connect(lambda message: self._on_project_load_failed(message, progress))
        self._load_worker.start()

    def _on_project_loaded(self, project, progress: QProgressDialog) -> None:
        progress.close()
        self._video_panel.set_loaded_project(project)

    def _on_project_load_failed(self, message: str, progress: QProgressDialog) -> None:
        progress.close()
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)
