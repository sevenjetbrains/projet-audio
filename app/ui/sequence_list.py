"""Liste des séquences : création, suppression, renommage, duplication, réorganisation (drag & drop).

Toutes les mutations passent par un QUndoStack (§17/§34) : chaque action pousse
une CallbackCommand réversible plutôt que d'appeler sequence_service directement.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QUndoStack
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
from app.ui.undo_commands import CallbackCommand
from app.utils.time_utils import format_timecode


class SequenceListWidget(QWidget):
    play_requested = Signal(str, str)
    sequences_changed = Signal()
    sequence_selected = Signal(str)
    selection_changed = Signal(list)

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None
        self._undo_stack = QUndoStack(self)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)

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

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    def set_project(self, project: Project) -> None:
        self._project = project
        self._undo_stack.clear()
        self._refresh()

    def add_sequence_from_selection(self, start: float, end: float) -> None:
        if self._project is None:
            return
        try:
            sequence = sequence_service.create_sequence(self._project, self._ffmpeg_service, start, end)
        except ValueError as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return
        except FFmpegExecutionError:
            QMessageBox.critical(self, "AudioCut Studio — Erreur", "Erreur lors de la création de la séquence.")
            return

        self._push_command(
            f"Créer « {sequence.name} »",
            redo_fn=lambda: sequence_service.insert_sequence(self._project, sequence),
            undo_fn=lambda: sequence_service.remove_sequence_from_list(self._project, sequence.id),
        )

    def _refresh(self) -> None:
        previous_id = self._current_sequence_id()

        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        if self._project is not None:
            for sequence in sorted(self._project.sequences, key=lambda seq: seq.order):
                status = " [traité]" if sequence.processed_audio_path else ""
                label = (
                    f"{sequence.order + 1}. {sequence.name}   "
                    f"{format_timecode(sequence.source_start)} → {format_timecode(sequence.source_end)}   "
                    f"({format_timecode(sequence.duration)}){status}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, sequence.id)
                self._list_widget.addItem(item)
                if sequence.id == previous_id:
                    self._list_widget.setCurrentItem(item)
        self._list_widget.blockSignals(False)

    def _push_command(self, description: str, redo_fn, undo_fn) -> None:
        def wrapped_redo():
            redo_fn()
            self._refresh()
            self.sequences_changed.emit()

        def wrapped_undo():
            undo_fn()
            self._refresh()
            self.sequences_changed.emit()

        self._undo_stack.push(CallbackCommand(description, wrapped_redo, wrapped_undo))

    def _current_sequence_id(self) -> str | None:
        item = self._list_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def get_sequence(self, sequence_id: str):
        if self._project is None:
            return None
        return next((seq for seq in self._project.sequences if seq.id == sequence_id), None)

    def current_sequence(self):
        sequence_id = self._current_sequence_id()
        return self.get_sequence(sequence_id) if sequence_id else None

    def selected_sequences(self) -> list:
        """Séquences sélectionnées (sélection multiple), dans l'ordre d'affichage."""
        selected = []
        for item in self._list_widget.selectedItems():
            sequence = self.get_sequence(item.data(Qt.ItemDataRole.UserRole))
            if sequence is not None:
                selected.append(sequence)
        return sorted(selected, key=lambda seq: seq.order)

    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.selected_sequences())

    def refresh(self) -> None:
        """Rafraîchit l'affichage (ex. après un traitement audio appliqué en externe)."""
        self._refresh()

    def _on_current_item_changed(self, current, _previous) -> None:
        if current is None:
            return
        self.sequence_selected.emit(current.data(Qt.ItemDataRole.UserRole))

    def _on_play_clicked(self) -> None:
        sequence = self.current_sequence()
        if sequence is None:
            return
        self.play_requested.emit(sequence.name, sequence.effective_audio_path)

    def _on_rename_clicked(self) -> None:
        sequence = self.current_sequence()
        if sequence is None or self._project is None:
            return
        new_name, ok = QInputDialog.getText(self, "Renommer la séquence", "Nom :", text=sequence.name)
        if not (ok and new_name.strip()):
            return

        old_name = sequence.name
        new_name = new_name.strip()
        self._push_command(
            f"Renommer « {old_name} » en « {new_name} »",
            redo_fn=lambda: sequence_service.rename_sequence(self._project, sequence.id, new_name),
            undo_fn=lambda: sequence_service.rename_sequence(self._project, sequence.id, old_name),
        )

    def _on_duplicate_clicked(self) -> None:
        if self._project is None:
            return
        originals = self.selected_sequences()
        if not originals:
            return
        duplicates = [sequence_service.create_duplicate(self._project, seq.id) for seq in originals]

        label = f"« {duplicates[0].name} »" if len(duplicates) == 1 else f"{len(duplicates)} séquences"

        def redo():
            for duplicate in duplicates:
                sequence_service.insert_sequence(self._project, duplicate)

        def undo():
            for duplicate in duplicates:
                sequence_service.remove_sequence_from_list(self._project, duplicate.id)

        self._push_command(f"Dupliquer {label}", redo_fn=redo, undo_fn=undo)

    def _on_delete_clicked(self) -> None:
        if self._project is None:
            return
        targets = self.selected_sequences()
        if not targets:
            return
        # Position d'origine de chaque séquence, pour la restaurer exactement à l'annulation.
        positions = [(seq, self._project.sequences.index(seq)) for seq in targets]

        label = f"« {targets[0].name} »" if len(targets) == 1 else f"{len(targets)} séquences"

        def redo():
            for seq, _index in positions:
                sequence_service.remove_sequence_from_list(self._project, seq.id)

        def undo():
            for seq, index in sorted(positions, key=lambda pair: pair[1]):
                sequence_service.insert_sequence(self._project, seq, index)

        self._push_command(f"Supprimer {label}", redo_fn=redo, undo_fn=undo)

    def _on_rows_moved(self, *_args) -> None:
        if self._project is None:
            return
        new_order = [
            self._list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list_widget.count())
        ]
        old_order = [seq.id for seq in sorted(self._project.sequences, key=lambda s: s.order)]
        if new_order == old_order:
            return

        self._push_command(
            "Réorganiser les séquences",
            redo_fn=lambda: sequence_service.reorder_sequences(self._project, new_order),
            undo_fn=lambda: sequence_service.reorder_sequences(self._project, old_order),
        )
