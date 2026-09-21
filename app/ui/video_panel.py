"""Bloc SOURCE : import du fichier, métadonnées de la vidéo, extraction de la piste audio."""

import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import SUPPORTED_VIDEO_FORMATS
from app.config.settings import FFmpegBinaries
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService, ProbeError
from app.services.project_service import create_project_for_video
from app.ui.design import card_layout, info_row, label
from app.utils.time_utils import format_timecode_fr
from app.workers.ffmpeg_worker import ExtractAudioWorker

_INFO_FIELDS = ("Durée", "Taille", "Vidéo", "Audio")
_SOURCE_NOTE = "Le fichier vidéo source n'est jamais modifié."


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024:
            return f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size:.1f} To".replace(".", ",")


def _video_filter() -> str:
    extensions = " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_FORMATS)
    return f"Vidéos ({extensions})"


def _describe_video(media_info) -> str:
    """« H.264 · 1920×1080 » — piste vidéo résumée en une ligne."""
    parts = [media_info.video_codec or "—"]
    if media_info.resolution:
        parts.append(f"{media_info.resolution[0]}×{media_info.resolution[1]}")
    return " · ".join(parts)


def _describe_audio(media_info) -> str:
    """« AAC · 48 kHz · st. » — piste audio résumée en une ligne."""
    channels = {1: "mono", 2: "st."}.get(media_info.channels, f"{media_info.channels} can.")
    return f"{media_info.audio_codec} · {media_info.sample_rate / 1000:g} kHz · {channels}"


class VideoPanel(QWidget):
    audio_ready = Signal(str, float)
    # Suivis par l'écran d'accueil, qui montre la progression de l'import tant qu'aucun projet n'est ouvert.
    extraction_started = Signal(str)
    extraction_progress = Signal(int)
    extraction_finished = Signal()

    def __init__(self, ffmpeg_binaries: FFmpegBinaries, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
        self._ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
        self._worker: ExtractAudioWorker | None = None
        self._project = None
        self._import_guard: Callable[[], bool] | None = None

        # Visible tant qu'aucune vidéo n'est chargée ; ensuite, l'import passe par la barre d'outils.
        self._import_button = QPushButton("Importer une vidéo")
        self._import_button.setProperty("accent", "true")
        self._import_button.clicked.connect(self._on_import_clicked)
        self._import_button.setToolTip("Importer une vidéo (Ctrl+O)")
        self._empty_label = label("Aucune vidéo importée.", "hintLabel")

        self._name_label = label("—", "titleLabel")
        self._name_label.setWordWrap(True)
        self._info_labels: dict[str, QLabel] = {}
        self._info_rows: dict[str, QWidget] = {}
        for field_label in _INFO_FIELDS:
            value_label = label("—", "valueLabel")
            self._info_labels[field_label] = value_label
            self._info_rows[field_label] = info_row(field_label, value_label)

        self._extraction_title = label("Extraction de la piste audio", "titleLabel")
        self._extraction_percent = label("0 %", "mutedLabel")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        self._status_label = label(_SOURCE_NOTE, "hintLabel")
        self._status_label.setWordWrap(True)

        self.setLayout(self._build_layout())
        self._show_metadata(False)

    # --- Construction de l'interface --------------------------------------

    def _build_layout(self) -> QVBoxLayout:
        self._extraction_card, extraction_layout = card_layout("success", spacing=7, margin=12)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._extraction_title)
        header.addStretch(1)
        header.addWidget(self._extraction_percent)
        extraction_layout.addLayout(header)
        extraction_layout.addWidget(self._progress_bar)
        extraction_layout.addWidget(self._status_label)
        self._extraction_card.hide()

        self._metadata = QWidget()
        metadata_layout = QVBoxLayout(self._metadata)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(7)
        metadata_layout.addWidget(self._name_label)
        for field_label in _INFO_FIELDS:
            metadata_layout.addWidget(self._info_rows[field_label])

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._empty_label)
        layout.addWidget(self._import_button)
        layout.addWidget(self._metadata)
        layout.addWidget(self._extraction_card)
        return layout

    def _show_metadata(self, loaded: bool) -> None:
        """Bascule entre l'état « aucune vidéo » et l'affichage des métadonnées."""
        self._metadata.setVisible(loaded)
        self._empty_label.setVisible(not loaded)
        self._import_button.setVisible(not loaded)

    # --- Accès ------------------------------------------------------------

    @property
    def project(self):
        return self._project

    @property
    def ffmpeg_service(self) -> FFmpegService:
        return self._ffmpeg_service

    @property
    def ffprobe_service(self) -> FFprobeService:
        return self._ffprobe_service

    @property
    def is_busy(self) -> bool:
        """Vrai pendant l'extraction audio (un nouvel import doit alors être refusé)."""
        return not self._import_button.isEnabled()

    def set_loaded_project(self, project) -> None:
        """Adopte un Project déjà entièrement régénéré (chargement depuis .acsproject)."""
        self._project = project
        self._display_metadata(project.source_video)
        self._finish_extraction_display()
        self.audio_ready.emit(project.original_audio_path, project.source_video.duration)

    def set_import_guard(self, guard: Callable[[], bool] | None) -> None:
        """Fonction appelée avant tout nouvel import ; si elle retourne False, l'import est abandonné."""
        self._import_guard = guard

    def trigger_import(self) -> None:
        self._on_import_clicked()

    # --- Import et extraction ---------------------------------------------

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer une vidéo", "", _video_filter())
        if path:
            self.import_video(path)

    def import_video(self, path: str) -> None:
        """Analyse la vidéo, crée le projet associé et lance l'extraction audio."""
        if self.is_busy:
            return
        if self._import_guard is not None and not self._import_guard():
            return

        try:
            media_info = self._ffprobe_service.probe(path)
        except ProbeError as exc:
            QMessageBox.critical(self, "AudioCut Studio — Erreur", str(exc))
            return

        self._display_metadata(media_info)
        self._project = create_project_for_video(media_info)
        self._start_extraction(media_info)

    def _display_metadata(self, media_info) -> None:
        self._name_label.setText(Path(media_info.path).name)
        self._info_labels["Durée"].setText(format_timecode_fr(media_info.duration))
        self._info_labels["Taille"].setText(_format_size(media_info.size_bytes))
        self._info_labels["Vidéo"].setText(_describe_video(media_info))
        self._info_labels["Audio"].setText(_describe_audio(media_info))
        self._show_metadata(True)

    def _start_extraction(self, media_info) -> None:
        out_wav_path = str(Path(self._project.temp_dir) / "source.wav")

        self._worker = ExtractAudioWorker(
            self._ffmpeg_service, media_info.path, out_wav_path, media_info.duration
        )
        self._worker.progress.connect(self._on_extraction_progress)
        self._worker.succeeded.connect(self._on_extraction_succeeded)
        self._worker.failed.connect(self._on_extraction_failed)
        self._worker.cancelled.connect(self._on_extraction_cancelled)

        self._import_button.setEnabled(False)
        self._extraction_card.setProperty("card", "true")
        self._extraction_title.setText("Extraction de la piste audio")
        self._progress_bar.setProperty("tone", "")
        self._progress_bar.setValue(0)
        self._extraction_percent.setText("0 %")
        self._progress_bar.show()
        self._extraction_card.show()
        self._repolish()
        self.extraction_started.emit(Path(media_info.path).name)
        self._worker.start()

    def cancel_extraction(self) -> None:
        """Interrompt l'extraction en cours ; sans effet si aucune n'est lancée."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def _on_extraction_progress(self, percent: int) -> None:
        self._progress_bar.setValue(percent)
        self._extraction_percent.setText(f"{percent} %")
        self.extraction_progress.emit(percent)

    def _finish_extraction_display(self) -> None:
        """Carte verte « Piste audio extraite — 100 % », état de repos après extraction."""
        self._extraction_title.setText("Piste audio extraite")
        self._extraction_percent.setText("100 %")
        self._progress_bar.setProperty("tone", "success")
        self._progress_bar.setValue(100)
        self._progress_bar.show()
        self._status_label.setText(_SOURCE_NOTE)
        self._extraction_card.setProperty("card", "success")
        self._extraction_card.show()
        self._repolish()

    def _repolish(self) -> None:
        """Réapplique la feuille de style après un changement de propriété dynamique."""
        for widget in (self._extraction_card, self._progress_bar):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _on_extraction_succeeded(self, out_wav_path: str) -> None:
        self._project.original_audio_path = out_wav_path
        self._import_button.setEnabled(True)
        self._finish_extraction_display()
        self.extraction_finished.emit()
        self.audio_ready.emit(out_wav_path, self._project.source_video.duration)

    def _on_extraction_failed(self, message: str) -> None:
        self._progress_bar.hide()
        self._import_button.setEnabled(True)
        self._extraction_title.setText("Échec de l'extraction audio")
        self._extraction_percent.setText("—")
        self._status_label.setText("Vérifiez que le fichier contient bien une piste audio lisible.")
        self._extraction_card.setProperty("card", "true")
        self._repolish()
        self.extraction_finished.emit()
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)

    def _on_extraction_cancelled(self) -> None:
        """Import abandonné : le projet à demi créé et son dossier temporaire ne doivent rien laisser."""
        temp_dir = self._project.temp_dir if self._project is not None else ""
        self._project = None
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._import_button.setEnabled(True)
        self._progress_bar.hide()
        self._extraction_card.hide()
        self._show_metadata(False)
        self.extraction_finished.emit()
