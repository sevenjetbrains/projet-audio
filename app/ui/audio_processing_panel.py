"""Panneau de traitement audio : nettoyage, EQ, compression, normalisation, gain, fades."""

import copy

from PySide6.QtCore import Signal
from PySide6.QtGui import QUndoStack
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

from app.config.audio_profiles import AUDIO_PROFILES, CUSTOM_PROFILE_LABEL
from app.models.audio_settings import AudioSettings
from app.models.project import Project
from app.models.sequence import Sequence
from app.services import audio_processor
from app.services.ffmpeg_service import FFmpegService
from app.ui.shortcuts import set_button_shortcut
from app.utils.progress import sub_progress
from app.ui.undo_commands import CallbackCommand
from app.workers.ffmpeg_worker import FFmpegTaskWorker


class AudioProcessingPanel(QWidget):
    processed = Signal()

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None
        self._sequence: Sequence | None = None
        self._worker: FFmpegTaskWorker | None = None
        self._selected_sequences: list[Sequence] = []
        self._undo_stack: QUndoStack | None = None
        self._pending: tuple[str, list[Sequence], list[tuple]] | None = None

        self._profile_combo = QComboBox()
        self._profile_combo.addItem(CUSTOM_PROFILE_LABEL)
        self._profile_combo.addItems(list(AUDIO_PROFILES.keys()))
        self._profile_combo.currentTextChanged.connect(self._on_profile_selected)

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

        self._silence_removal_cb = QCheckBox("Suppression des silences")
        self._silence_threshold_spin = QDoubleSpinBox()
        self._silence_threshold_spin.setRange(-60.0, -10.0)
        self._silence_threshold_spin.setValue(-35.0)
        self._silence_threshold_spin.setSuffix(" dB")
        self._silence_min_duration_spin = QDoubleSpinBox()
        self._silence_min_duration_spin.setRange(0.05, 5.0)
        self._silence_min_duration_spin.setSingleStep(0.05)
        self._silence_min_duration_spin.setValue(0.5)
        self._silence_min_duration_spin.setSuffix(" s")
        self._silence_keep_padding_spin = QDoubleSpinBox()
        self._silence_keep_padding_spin.setRange(0.0, 2.0)
        self._silence_keep_padding_spin.setSingleStep(0.05)
        self._silence_keep_padding_spin.setValue(0.1)
        self._silence_keep_padding_spin.setSuffix(" s")

        self._apply_button = QPushButton("Appliquer")
        self._apply_button.clicked.connect(self._on_apply_clicked)
        self._apply_selection_button = QPushButton("Appliquer à la sélection")
        self._apply_selection_button.setEnabled(False)
        self._apply_selection_button.clicked.connect(self._on_apply_selection_clicked)
        self._reset_button = QPushButton("Réinitialiser")
        self._reset_button.clicked.connect(self._on_reset_clicked)

        set_button_shortcut(self._apply_button, "Ctrl+Return", "Appliquer le traitement à la séquence")
        set_button_shortcut(self._apply_selection_button, "Ctrl+Shift+Return", "Appliquer le traitement à la sélection")
        set_button_shortcut(self._reset_button, "Ctrl+R", "Réinitialiser le traitement")

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()
        self._status_label = QLabel("Sélectionnez une séquence.")

        form = QFormLayout()
        form.addRow("Profil :", self._profile_combo)
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

        form.addRow(self._silence_removal_cb)
        form.addRow("Seuil silence :", self._silence_threshold_spin)
        form.addRow("Durée min. silence :", self._silence_min_duration_spin)
        form.addRow("Marge conservée :", self._silence_keep_padding_spin)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self._apply_button)
        buttons_row.addWidget(self._apply_selection_button)
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

    def set_undo_stack(self, undo_stack: QUndoStack | None) -> None:
        """Pile Undo/Redo partagée avec la liste des séquences : traitements et réinitialisations y sont annulables."""
        self._undo_stack = undo_stack

    @staticmethod
    def _capture(sequence: Sequence) -> tuple:
        return (copy.deepcopy(sequence.audio_settings), sequence.processed_audio_path)

    @staticmethod
    def _restore(sequence: Sequence, state: tuple) -> None:
        sequence.audio_settings = copy.deepcopy(state[0])
        sequence.processed_audio_path = state[1]

    def _push_state_change(self, description: str, sequences: list[Sequence], before: list[tuple], after: list[tuple]) -> None:
        """Enregistre le passage de `before` à `after` comme une seule action annulable."""

        def apply(states: list[tuple]) -> None:
            for sequence, state in zip(sequences, states):
                self._restore(sequence, state)
            if self._sequence in sequences:
                self._load_settings(self._sequence.audio_settings)
            self.processed.emit()

        if self._undo_stack is None:
            apply(after)
            return
        self._undo_stack.push(CallbackCommand(description, lambda: apply(after), lambda: apply(before)))

    def set_project(self, project: Project) -> None:
        self._project = project

    def set_selected_sequences(self, sequences: list[Sequence]) -> None:
        """Séquences ciblées par « Appliquer à la sélection » (actif dès 2 séquences sélectionnées)."""
        self._selected_sequences = list(sequences)
        count = len(self._selected_sequences)
        self._apply_selection_button.setEnabled(count > 1)
        self._apply_selection_button.setText(f"Appliquer à la sélection ({count})" if count > 1 else "Appliquer à la sélection")

    def set_sequence(self, sequence: Sequence | None) -> None:
        self._sequence = sequence
        self.setEnabled(sequence is not None)
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentText(CUSTOM_PROFILE_LABEL)
        self._profile_combo.blockSignals(False)
        self._load_settings(sequence.audio_settings if sequence else AudioSettings())
        self._status_label.setText(
            f"Séquence : {sequence.name}" if sequence else "Sélectionnez une séquence."
        )

    def _on_profile_selected(self, profile_name: str) -> None:
        settings = AUDIO_PROFILES.get(profile_name)
        if settings is not None:
            self._load_settings(settings)

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
        self._silence_removal_cb.setChecked(settings.silence_removal)
        self._silence_threshold_spin.setValue(settings.silence_threshold_db)
        self._silence_min_duration_spin.setValue(settings.silence_min_duration)
        self._silence_keep_padding_spin.setValue(settings.silence_keep_padding)

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
            silence_removal=self._silence_removal_cb.isChecked(),
            silence_threshold_db=self._silence_threshold_spin.value(),
            silence_min_duration=self._silence_min_duration_spin.value(),
            silence_keep_padding=self._silence_keep_padding_spin.value(),
        )

    def _on_apply_clicked(self) -> None:
        if self._sequence is None or self._project is None:
            return

        sequence = self._sequence
        self._pending = (f"Traiter « {sequence.name} »", [sequence], [self._capture(sequence)])
        sequence.audio_settings = self._read_settings()

        self._set_busy(True, "Traitement en cours…")

        project = self._project
        self._worker = FFmpegTaskWorker(
            lambda report: audio_processor.process_sequence(project, sequence, self._ffmpeg_service, report),
            with_progress=True,
        )
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.succeeded.connect(self._on_processing_succeeded)
        self._worker.failed.connect(self._on_processing_failed)
        self._worker.start()

    def _on_apply_selection_clicked(self) -> None:
        """Applique les réglages courants à toutes les séquences sélectionnées (traitement séquentiel)."""
        if self._project is None or len(self._selected_sequences) < 2:
            return

        settings = self._read_settings()
        sequences = list(self._selected_sequences)
        self._pending = (f"Traiter {len(sequences)} séquences", sequences, [self._capture(seq) for seq in sequences])
        for sequence in sequences:
            sequence.audio_settings = copy.deepcopy(settings)

        self._set_busy(True, f"Traitement de {len(sequences)} séquences…")
        project = self._project
        self._worker = FFmpegTaskWorker(
            lambda report: [
                audio_processor.process_sequence(
                    project, seq, self._ffmpeg_service, sub_progress(report, i / len(sequences), (i + 1) / len(sequences))
                )
                for i, seq in enumerate(sequences)
            ],
            with_progress=True,
        )
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.succeeded.connect(self._on_processing_succeeded)
        self._worker.failed.connect(self._on_processing_failed)
        self._worker.start()

    def _set_busy(self, busy: bool, message: str) -> None:
        self._apply_button.setEnabled(not busy)
        self._apply_selection_button.setEnabled(not busy and len(self._selected_sequences) > 1)
        if busy:
            self._progress_bar.setValue(0)
        self._progress_bar.setVisible(busy)
        self._status_label.setText(message)

    def _on_processing_succeeded(self, _result) -> None:
        self._set_busy(False, "Traitement appliqué.")
        pending, self._pending = self._pending, None
        if pending is None:
            self.processed.emit()
            return
        description, sequences, before = pending
        self._push_state_change(description, sequences, before, [self._capture(seq) for seq in sequences])

    def _on_processing_failed(self, message: str) -> None:
        # Le traitement a échoué : on rétablit les réglages/fichiers d'avant pour rester cohérent.
        pending, self._pending = self._pending, None
        if pending is not None:
            _description, sequences, before = pending
            for sequence, state in zip(sequences, before):
                self._restore(sequence, state)
        self._set_busy(False, "Échec du traitement.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def _on_reset_clicked(self) -> None:
        if self._sequence is None:
            return
        sequence = self._sequence
        before = self._capture(sequence)
        audio_processor.reset_processing(sequence)
        after = self._capture(sequence)
        self._push_state_change(f"Réinitialiser « {sequence.name} »", [sequence], [before], [after])
        self._status_label.setText("Traitement réinitialisé.")
