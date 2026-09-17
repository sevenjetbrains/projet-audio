"""Dialogue d'export : choix du format, de la qualité, du nom et du dossier de destination."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
}


class ExportDialog(QDialog):
    def __init__(self, project: Project, ffmpeg_service: FFmpegService, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exporter le résultat final")
        self._project = project
        self._ffmpeg_service = ffmpeg_service
        self._worker: FFmpegTaskWorker | None = None

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
        self._on_format_changed(self._format_combo.currentText())

        self._export_button = QPushButton("Exporter")
        self._export_button.clicked.connect(self._on_export_clicked)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.hide()

        self._status_label = QLabel("")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Fichier de destination :"))
        layout.addLayout(path_layout)
        layout.addWidget(QLabel("Format :"))
        layout.addWidget(self._format_combo)
        layout.addWidget(QLabel("Qualité :"))
        layout.addWidget(self._quality_combo)
        layout.addWidget(self._export_button)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        self.setLayout(layout)

    def _on_format_changed(self, fmt: str) -> None:
        self._quality_combo.clear()
        for label, _code in _QUALITY_OPTIONS[fmt]:
            self._quality_combo.addItem(label)

    def _selected_quality_code(self) -> str:
        fmt = self._format_combo.currentText()
        index = self._quality_combo.currentIndex()
        return _QUALITY_OPTIONS[fmt][index][1]

    def _on_browse_clicked(self) -> None:
        fmt = self._format_combo.currentText().lower()
        path, _ = QFileDialog.getSaveFileName(self, "Exporter vers…", "", f"Fichier {fmt.upper()} (*.{fmt})")
        if path:
            self._path_edit.setText(path)

    def _on_export_clicked(self) -> None:
        out_path = self._path_edit.text().strip()
        if not out_path:
            QMessageBox.warning(self, "AudioCut Studio", "Veuillez choisir un fichier de destination.")
            return

        fmt = self._format_combo.currentText()
        quality = self._selected_quality_code()

        from app.services.export_service import export_project

        self._export_button.setEnabled(False)
        self._progress_bar.show()
        self._status_label.setText("Fusion et export en cours…")

        self._worker = FFmpegTaskWorker(
            lambda: export_project(self._project, self._ffmpeg_service, out_path, fmt, quality)
        )
        self._worker.succeeded.connect(lambda _: self._on_export_succeeded(out_path))
        self._worker.failed.connect(self._on_export_failed)
        self._worker.start()

    def _on_export_succeeded(self, out_path: str) -> None:
        self._progress_bar.hide()
        self._export_button.setEnabled(True)
        self._status_label.setText(f"Export terminé : {out_path}")
        QMessageBox.information(self, "AudioCut Studio", f"Export terminé avec succès :\n{out_path}")
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
