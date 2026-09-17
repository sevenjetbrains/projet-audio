"""Liste des séquences : création, suppression, renommage, duplication, réorganisation (drag & drop)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.project import Project
from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegExecutionError, FFmpegService
from app.utils.time_utils import format_timecode


class SequenceListWidget(QWidget):
    play_requested = Signal(str, str)
    sequences_changed = Signal()

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None

        self._list_widget = QListWidget()
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list_widget.model().rowsMoved.connect(self._on_rows_moved)

        play_button = QPushButton("▶ Lire")
        play_button.clicked.connect(self._on_play_clicked)
        rename_button = QPushButton("Renommer")
        rename_button.clicked.connect(self._on_rename_clicked)
        duplicate_button = QPushButton("Dupliquer")
        duplicate_button.clicked.connect(self._on_duplicate_clicked)
        delete_button = QPushButton("Supprimer")
        delete_button.clicked.connect(self._on_delete_clicked)

        buttons_layout = QHBoxLayout()
        for button in (play_button, rename_button, duplicate_button, delete_button):
            buttons_layout.addWidget(button)

        layout = QVBoxLayout()
        layout.addWidget(self._list_widget)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def set_project(self, project: Project) -> None:
        self._project = project
        self._refresh()

    def add_sequence_from_selection(self, start: float, end: float) -> None:
        if self._project is None:
            return
        try:
            sequence_service.add_sequence(self._project, self._ffmpeg_service, start, end)
        except ValueError as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return
        except FFmpegExecutionError:
            QMessageBox.critical(self, "AudioCut Studio — Erreur", "Erreur lors de la création de la séquence.")
            return

        self._refresh()
        self.sequences_changed.emit()

    def _refresh(self) -> None:
        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        if self._project is not None:
            for sequence in sorted(self._project.sequences, key=lambda seq: seq.order):
                label = (
                    f"{sequence.order + 1}. {sequence.name}   "
                    f"{format_timecode(sequence.source_start)} → {format_timecode(sequence.source_end)}   "
                    f"({format_timecode(sequence.duration)})"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, sequence.id)
                self._list_widget.addItem(item)
        self._list_widget.blockSignals(False)

    def _current_sequence_id(self) -> str | None:
        item = self._list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_play_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is None or self._project is None:
            return
        sequence = next(seq for seq in self._project.sequences if seq.id == sequence_id)
        self.play_requested.emit(sequence.name, sequence.audio_path)

    def _on_rename_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is None or self._project is None:
            return
        sequence = next(seq for seq in self._project.sequences if seq.id == sequence_id)
        new_name, ok = QInputDialog.getText(self, "Renommer la séquence", "Nom :", text=sequence.name)
        if ok and new_name.strip():
            sequence_service.rename_sequence(self._project, sequence_id, new_name.strip())
            self._refresh()
            self.sequences_changed.emit()

    def _on_duplicate_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is None or self._project is None:
            return
        sequence_service.duplicate_sequence(self._project, sequence_id)
        self._refresh()
        self.sequences_changed.emit()

    def _on_delete_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is None or self._project is None:
            return
        sequence_service.remove_sequence(self._project, sequence_id)
        self._refresh()
        self.sequences_changed.emit()

    def _on_rows_moved(self, *_args) -> None:
        if self._project is None:
            return
        ordered_ids = [
            self._list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list_widget.count())
        ]
        sequence_service.reorder_sequences(self._project, ordered_ids)
        self._refresh()
        self.sequences_changed.emit()
