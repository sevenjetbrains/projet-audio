"""Panneau d'import vidéo : sélection du fichier, affichage des métadonnées, extraction audio."""

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
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
from app.utils.time_utils import format_timecode
from app.workers.ffmpeg_worker import ExtractAudioWorker


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("o", "Ko", "Mo", "Go"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} To"


def _video_filter() -> str:
    extensions = " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_FORMATS)
    return f"Vidéos ({extensions})"


class VideoPanel(QWidget):
    def __init__(self, ffmpeg_binaries: FFmpegBinaries, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
        self._ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
        self._worker: ExtractAudioWorker | None = None
        self._project = None

        self._import_button = QPushButton("Importer une vidéo")
        self._import_button.clicked.connect(self._on_import_clicked)

        self._info_labels: dict[str, QLabel] = {}
        form_layout = QFormLayout()
        for field_label in (
            "Nom", "Durée", "Taille", "Résolution",
            "Codec vidéo", "Codec audio", "Fréquence d'échantillonnage", "Canaux",
        ):
            value_label = QLabel("—")
            self._info_labels[field_label] = value_label
            form_layout.addRow(f"{field_label} :", value_label)

        self._status_label = QLabel("Aucune vidéo importée.")
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(self._import_button)
        layout.addLayout(form_layout)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

    def _on_import_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importer une vidéo", "", _video_filter())
        if not path:
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
        self._info_labels["Nom"].setText(Path(media_info.path).name)
        self._info_labels["Durée"].setText(format_timecode(media_info.duration))
        self._info_labels["Taille"].setText(_format_size(media_info.size_bytes))
        resolution = f"{media_info.resolution[0]}x{media_info.resolution[1]}" if media_info.resolution else "—"
        self._info_labels["Résolution"].setText(resolution)
        self._info_labels["Codec vidéo"].setText(media_info.video_codec or "—")
        self._info_labels["Codec audio"].setText(media_info.audio_codec)
        self._info_labels["Fréquence d'échantillonnage"].setText(f"{media_info.sample_rate} Hz")
        self._info_labels["Canaux"].setText(str(media_info.channels))

    def _start_extraction(self, media_info) -> None:
        out_wav_path = str(Path(self._project.temp_dir) / "source.wav")

        self._worker = ExtractAudioWorker(
            self._ffmpeg_service, media_info.path, out_wav_path, media_info.duration
        )
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.succeeded.connect(self._on_extraction_succeeded)
        self._worker.failed.connect(self._on_extraction_failed)

        self._import_button.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_label.setText("Extraction de l'audio en cours…")
        self._worker.start()

    def _on_extraction_succeeded(self, out_wav_path: str) -> None:
        self._project.original_audio_path = out_wav_path
        self._progress_bar.hide()
        self._import_button.setEnabled(True)
        self._status_label.setText(f"Audio extrait : {out_wav_path}")

    def _on_extraction_failed(self, message: str) -> None:
        self._progress_bar.hide()
        self._import_button.setEnabled(True)
        self._status_label.setText("Échec de l'extraction audio.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)
