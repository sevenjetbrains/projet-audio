"""Panneau de traitement audio : nettoyage, EQ, compression, normalisation, gain, fades."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.audio_settings import AudioSettings
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import audio_processor
from app.services.ffmpeg_service import FFmpegService
from app.workers.ffmpeg_worker import FFmpegTaskWorker


class AudioProcessingPanel(QWidget):
    processed = Signal()

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None
        self._sequence: Sequence | None = None
        self._worker: FFmpegTaskWorker | None = None

        self._noise_cb = QCheckBox("Réduction du bruit")
        self._noise_level_combo = QComboBox()
        self._noise_level_combo.addItems(["faible", "moyenne", "forte"])

        self._dehum_cb = QCheckBox("De-hum")
        self._dehum_freq_combo = QComboBox()
        self._dehum_freq_combo.addItems(["50 Hz", "60 Hz"])

        self._declick_cb = QCheckBox("De-click")

        self._bass_spin = self._make_db_spin()
        self._mid_spin = self._make_db_spin()
        self._treble_spin = self._make_db_spin()

        self._compression_cb = QCheckBox("Compression (voix)")

        self._normalize_cb = QCheckBox("Normalisation")
        self._normalize_mode_combo = QComboBox()
        self._normalize_mode_combo.addItems(["peak", "loudness"])
        self._target_lufs_spin = QDoubleSpinBox()
        self._target_lufs_spin.setRange(-30.0, -5.0)
        self._target_lufs_spin.setValue(-16.0)
        self._target_lufs_spin.setSuffix(" LUFS")

        self._gain_spin = self._make_db_spin()
        self._fade_in_spin = self._make_seconds_spin()
        self._fade_out_spin = self._make_seconds_spin()

        self._apply_button = QPushButton("Appliquer")
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._reset_button = QPushButton("Réinitialiser")
        self._reset_button.clicked.connect(self._on_reset_clicked)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.hide()
        self._status_label = QLabel("Sélectionnez une séquence.")

        form = QFormLayout()
        noise_row = QHBoxLayout()
        noise_row.addWidget(self._noise_cb)
        noise_row.addWidget(self._noise_level_combo)
        form.addRow(noise_row)

        dehum_row = QHBoxLayout()
        dehum_row.addWidget(self._dehum_cb)
        dehum_row.addWidget(self._dehum_freq_combo)
        form.addRow(dehum_row)

        form.addRow(self._declick_cb)
        form.addRow("Basses (dB) :", self._bass_spin)
        form.addRow("Médiums (dB) :", self._mid_spin)
        form.addRow("Aigus (dB) :", self._treble_spin)
        form.addRow(self._compression_cb)

        normalize_row = QHBoxLayout()
        normalize_row.addWidget(self._normalize_cb)
        normalize_row.addWidget(self._normalize_mode_combo)
        normalize_row.addWidget(self._target_lufs_spin)
        form.addRow(normalize_row)

        form.addRow("Gain (dB) :", self._gain_spin)
        form.addRow("Fade In (s) :", self._fade_in_spin)
        form.addRow("Fade Out (s) :", self._fade_out_spin)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self._apply_button)
        buttons_row.addWidget(self._reset_button)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(buttons_row)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        self.setLayout(layout)

        self.setEnabled(False)

    @staticmethod
    def _make_db_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-12.0, 12.0)
        spin.setSuffix(" dB")
        return spin

    @staticmethod
    def _make_seconds_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 10.0)
        spin.setSingleStep(0.1)
        spin.setSuffix(" s")
        return spin

    def set_project(self, project: Project) -> None:
        self._project = project

    def set_sequence(self, sequence: Sequence | None) -> None:
        self._sequence = sequence
        self.setEnabled(sequence is not None)
        self._load_settings(sequence.audio_settings if sequence else AudioSettings())
        self._status_label.setText(
            f"Séquence : {sequence.name}" if sequence else "Sélectionnez une séquence."
        )

    def _load_settings(self, settings: AudioSettings) -> None:
        self._noise_cb.setChecked(settings.noise_reduction)
        self._noise_level_combo.setCurrentText(settings.noise_reduction_level)
        self._dehum_cb.setChecked(settings.de_hum)
        self._dehum_freq_combo.setCurrentText(f"{settings.de_hum_freq} Hz")
        self._declick_cb.setChecked(settings.de_click)
        self._bass_spin.setValue(settings.eq_bass_db)
        self._mid_spin.setValue(settings.eq_mid_db)
        self._treble_spin.setValue(settings.eq_treble_db)
        self._compression_cb.setChecked(settings.compression)
        self._normalize_cb.setChecked(settings.normalize)
        self._normalize_mode_combo.setCurrentText(settings.normalize_mode)
        self._target_lufs_spin.setValue(settings.normalize_target_lufs)
        self._gain_spin.setValue(settings.gain)
        self._fade_in_spin.setValue(settings.fade_in)
        self._fade_out_spin.setValue(settings.fade_out)

    def _read_settings(self) -> AudioSettings:
        return AudioSettings(
            gain=self._gain_spin.value(),
            fade_in=self._fade_in_spin.value(),
            fade_out=self._fade_out_spin.value(),
            noise_reduction=self._noise_cb.isChecked(),
            noise_reduction_level=self._noise_level_combo.currentText(),
            de_hum=self._dehum_cb.isChecked(),
            de_hum_freq=int(self._dehum_freq_combo.currentText().split()[0]),
            de_click=self._declick_cb.isChecked(),
            eq_bass_db=self._bass_spin.value(),
            eq_mid_db=self._mid_spin.value(),
            eq_treble_db=self._treble_spin.value(),
            compression=self._compression_cb.isChecked(),
            normalize=self._normalize_cb.isChecked(),
            normalize_mode=self._normalize_mode_combo.currentText(),
            normalize_target_lufs=self._target_lufs_spin.value(),
        )

    def _on_apply_clicked(self) -> None:
        if self._sequence is None or self._project is None:
            return

        self._sequence.audio_settings = self._read_settings()

        self._apply_button.setEnabled(False)
        self._progress_bar.show()
        self._status_label.setText("Traitement en cours…")

        sequence = self._sequence
        project = self._project
        self._worker = FFmpegTaskWorker(
            lambda: audio_processor.process_sequence(project, sequence, self._ffmpeg_service)
        )
        self._worker.succeeded.connect(self._on_processing_succeeded)
        self._worker.failed.connect(self._on_processing_failed)
        self._worker.start()

    def _on_processing_succeeded(self, _result) -> None:
        self._progress_bar.hide()
        self._apply_button.setEnabled(True)
        self._status_label.setText("Traitement appliqué.")
        self.processed.emit()

    def _on_processing_failed(self, message: str) -> None:
        self._progress_bar.hide()
        self._apply_button.setEnabled(True)
        self._status_label.setText("Échec du traitement.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def _on_reset_clicked(self) -> None:
        if self._sequence is None:
            return
        audio_processor.reset_processing(self._sequence)
        self._load_settings(self._sequence.audio_settings)
        self._status_label.setText("Traitement réinitialisé.")
        self.processed.emit()
