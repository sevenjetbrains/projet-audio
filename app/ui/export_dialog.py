"""Dialogue d'export : choix du format, de la qualité, du nom et du dossier de destination."""

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from app.models.project import Project
from app.services.ffmpeg_service import FFmpegService
from app.workers.ffmpeg_worker import FFmpegTaskWorker

_QUALITY_OPTIONS = {
    "WAV": [("16 bits", "16"), ("24 bits", "24")],
    "MP3": [("128 kbps", "128"), ("192 kbps", "192"), ("256 kbps", "256"), ("320 kbps", "320")],
    "FLAC": [("16 bits", "16"), ("24 bits", "24")],
    "M4A": [("128 kbps", "128"), ("192 kbps", "192"), ("256 kbps", "256"), ("320 kbps", "320")],
    "OGG": [("Standard (q3)", "3"), ("Bonne (q5)", "5"), ("Haute (q7)", "7")],
    "OPUS": [("64 kbps", "64"), ("96 kbps", "96"), ("128 kbps", "128"), ("192 kbps", "192")],
}


class ExportDialog(QDialog):
    def __init__(self, project: Project, ffmpeg_service: FFmpegService, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exporter le résultat final")
        self._project = project
        self._ffmpeg_service = ffmpeg_service
        self._worker: FFmpegTaskWorker | None = None
        self._exported_folder = ""

        self._path_edit = QLineEdit()
        browse_button = QPushButton("Parcourir…")
        browse_button.clicked.connect(self._on_browse_clicked)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self._path_edit)
        path_layout.addWidget(browse_button)

        self._format_combo = QComboBox()
        self._format_combo.addItems(list(_QUALITY_OPTIONS.keys()))
        self._format_combo.currentTextChanged.connect(self._on_format_changed)

        self._quality_combo = QComboBox()
        self._auto_path = ""

        self._separate_cb = QCheckBox("Un fichier par séquence (destination : dossier)")
        self._separate_cb.toggled.connect(self._on_separate_toggled)

        self._normalize_cb = QCheckBox("Normaliser le volume (loudness)")
        self._normalize_cb.toggled.connect(lambda checked: self._lufs_spin.setEnabled(checked))
        self._lufs_spin = QDoubleSpinBox()
        self._lufs_spin.setRange(-30.0, -5.0)
        self._lufs_spin.setSingleStep(1.0)
        self._lufs_spin.setValue(-16.0)
        self._lufs_spin.setSuffix(" LUFS")
        self._lufs_spin.setEnabled(False)
        normalize_row = QHBoxLayout()
        normalize_row.addWidget(self._normalize_cb)
        normalize_row.addWidget(self._lufs_spin)

        self._open_folder_cb = QCheckBox("Ouvrir le dossier à la fin de l'export")

        self._export_button = QPushButton("Exporter")
        self._export_button.clicked.connect(self._on_export_clicked)
        self._export_button.setDefault(True)
        self._export_button.setToolTip("Lancer l'export (Entrée)")

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()

        self._status_label = QLabel("")

        layout = QVBoxLayout()
        self._destination_label = QLabel("Fichier de destination :")
        layout.addWidget(self._destination_label)
        layout.addLayout(path_layout)
        layout.addWidget(QLabel("Format :"))
        layout.addWidget(self._format_combo)
        layout.addWidget(QLabel("Qualité :"))
        layout.addWidget(self._quality_combo)
        layout.addWidget(self._separate_cb)
        layout.addLayout(normalize_row)
        layout.addWidget(self._open_folder_cb)
        layout.addWidget(self._export_button)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        self.setLayout(layout)

        self._on_format_changed(self._format_combo.currentText())

    def _suggested_path(self) -> str:
        """Destination proposée : à côté de la vidéo source, nommée d'après elle."""
        source = self._project.source_video
        if source is None:
            return ""
        video = Path(source.path)
        if self._separate_cb.isChecked():
            return str(video.parent / f"{video.stem}_sequences")
        return str(video.parent / f"{video.stem}_audio.{self._format_combo.currentText().lower()}")

    def _refresh_suggested_path(self) -> None:
        """Met à jour la destination proposée sans écraser un chemin saisi par l'utilisateur."""
        current = self._path_edit.text().strip()
        if current and current != self._auto_path:
            return
        self._auto_path = self._suggested_path()
        self._path_edit.setText(self._auto_path)

    def _on_format_changed(self, fmt: str) -> None:
        self._quality_combo.clear()
        for label, _code in _QUALITY_OPTIONS[fmt]:
            self._quality_combo.addItem(label)
        self._refresh_suggested_path()

    def _on_separate_toggled(self, checked: bool) -> None:
        self._destination_label.setText("Dossier de destination :" if checked else "Fichier de destination :")
        self._path_edit.clear()
        self._refresh_suggested_path()

    def _selected_quality_code(self) -> str:
        fmt = self._format_combo.currentText()
        index = self._quality_combo.currentIndex()
        return _QUALITY_OPTIONS[fmt][index][1]

    def _on_browse_clicked(self) -> None:
        if self._separate_cb.isChecked():
            path = QFileDialog.getExistingDirectory(self, "Dossier d'export")
            if path:
                self._path_edit.setText(path)
            return
        fmt = self._format_combo.currentText().lower()
        path, _ = QFileDialog.getSaveFileName(self, "Exporter vers…", "", f"Fichier {fmt.upper()} (*.{fmt})")
        if path:
            self._path_edit.setText(path)

    def _on_export_clicked(self) -> None:
        out_path = self._path_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "AudioCut Studio", "Veuillez choisir une destination.")
            return

        fmt = self._format_combo.currentText()
        quality = self._selected_quality_code()

        from app.services.export_service import export_project, export_sequences_separately

        separate = self._separate_cb.isChecked()
        self._exported_folder = out_path if separate else str(Path(out_path).parent)
        normalize_lufs = self._lufs_spin.value() if self._normalize_cb.isChecked() else None
        self._export_button.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_label.setText("Export en cours…")

        if separate:
            task = lambda report: export_sequences_separately(
                self._project, self._ffmpeg_service, out_path, fmt, quality, normalize_lufs, on_progress=report
            )
        else:
            task = lambda report: export_project(
                self._project, self._ffmpeg_service, out_path, fmt, quality, normalize_lufs, on_progress=report
            )
        self._worker = FFmpegTaskWorker(task, with_progress=True)
        self._worker.progress.connect(self._progress_bar.setValue)
        self._worker.succeeded.connect(lambda _: self._on_export_succeeded(out_path))
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()

    def _on_export_succeeded(self, out_path: str) -> None:
        self._progress_bar.hide()
        self._export_button.setEnabled(True)
        self._status_label.setText(f"Export terminé : {out_path}")
        QMessageBox.information(self, "AudioCut Studio", f"Export terminé avec succès :\n{out_path}")
        if self._open_folder_cb.isChecked():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._exported_folder))
        self.accept()

    def closeEvent(self, event) -> None:
        """Empêche la fermeture pendant un export en cours (§21 : pas de fermeture pendant un traitement)."""
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def _on_export_failed(self, message: str) -> None:
        self._progress_bar.hide()
        self._export_button.setEnabled(True)
        self._status_label.setText("Échec de l'export.")
        QMessageBox.critical(self, "AudioCut Studio — Erreur", message)
