"""Liste des séquences : création, suppression, renommage, duplication, réorganisation (drag & drop).

Toutes les mutations passent par un QUndoStack (§17/§34) : chaque action pousse
une CallbackCommand réversible plutôt que d'appeler sequence_service directement.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.themes import Theme
from app.models.project import Project
from app.services import sequence_service
from app.services.ffmpeg_service import FFmpegExecutionError, FFmpegService
from app.ui.design import icon_button, label, section_label
from app.ui.sequence_row_delegate import ROW_DATA_ROLE, SequenceRow, SequenceRowDelegate
from app.ui.shortcuts import set_button_shortcut
from app.ui.undo_commands import CallbackCommand
from app.utils.time_utils import format_clock, format_timecode

_COLUMN_HEADERS = ("NOM", "DÉBUT", "DURÉE", "STATUT")
# Largeurs des colonnes de droite, alignées sur celles du delegate.
_HEADER_STRETCH = (1, 0, 0, 0)
_HEADER_WIDTHS = (0, 78, 66, 54)


class SequenceListWidget(QWidget):
    play_requested = Signal(str, str, float)
    sequences_changed = Signal()
    sequence_selected = Signal(str)
    selection_changed = Signal(list)
    edit_bounds_requested = Signal(str)
    split_requested = Signal(str)
    original_toggled = Signal(bool)
    processing_requested = Signal()

    def __init__(self, ffmpeg_service: FFmpegService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._project: Project | None = None
        self._undo_stack = QUndoStack(self)

        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list_widget.setMouseTracking(True)
        self._list_widget.setUniformItemSizes(True)
        self._delegate = SequenceRowDelegate(self._list_widget)
        self._list_widget.setItemDelegate(self._delegate)
        self._list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self._list_widget.currentItemChanged.connect(self._on_current_item_changed)
        self._list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._count_label = label("Séquences", "titleLabel")
        self._empty_label = label(
            "Aucune séquence.\nSélectionnez une plage sur la waveform,\npuis « Créer la séquence ».", "hintLabel"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)

        self._play_button = icon_button("play")
        self._play_button.clicked.connect(self._on_play_clicked)
        set_button_shortcut(self._play_button, "Ctrl+L", "Lire la séquence")
        self._rename_button = QPushButton("Renommer")
        self._rename_button.clicked.connect(self._on_rename_clicked)
        set_button_shortcut(self._rename_button, "F2")
        self._duplicate_button = QPushButton("Dupliquer")
        self._duplicate_button.clicked.connect(self._on_duplicate_clicked)
        set_button_shortcut(self._duplicate_button, "Ctrl+D")
        self._bounds_button = QPushButton("Bornes")
        self._bounds_button.clicked.connect(self._on_bounds_clicked)
        set_button_shortcut(self._bounds_button, "F3", "Ajuster les bornes de la séquence dans la sélection")
        self._split_button = QPushButton("Diviser")
        self._split_button.clicked.connect(self._on_split_clicked)
        set_button_shortcut(self._split_button, "S", "Diviser la séquence à la tête de lecture")
        self._original_button = QPushButton("Original")
        self._original_button.setCheckable(True)
        self._original_button.toggled.connect(self.original_toggled.emit)
        set_button_shortcut(
            self._original_button, "Ctrl+B",
            "Écouter la version d'origine, sans traitement, pour comparer avec la version traitée (A/B)",
        )
        self._delete_button = icon_button("trash")
        self._delete_button.setProperty("danger", "true")
        self._delete_button.clicked.connect(self._on_delete_clicked)
        set_button_shortcut(self._delete_button, "Delete", "Supprimer")

        self._processing_button = QPushButton("Appliquer un traitement…")
        self._processing_button.clicked.connect(self.processing_requested.emit)
        self._processing_button.setToolTip("Ouvrir le panneau de traitement audio pour la sélection")

        self.setLayout(self._build_layout())
        self._refresh()

    # --- Construction de l'interface --------------------------------------

    def _build_layout(self) -> QVBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._count_label)
        header.addStretch(1)
        header.addWidget(label("glisser pour réorganiser", "hintLabel"))

        self._columns_header = QWidget()
        columns = QHBoxLayout(self._columns_header)
        columns.setContentsMargins(13, 0, 10, 0)
        columns.setSpacing(0)
        for title, stretch, width in zip(_COLUMN_HEADERS, _HEADER_STRETCH, _HEADER_WIDTHS):
            column = section_label(title)
            column.setObjectName("sequenceTableHeader")
            if width:
                column.setFixedWidth(width)
            columns.addWidget(column, stretch)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self._play_button)
        buttons.addWidget(self._rename_button, 1)
        buttons.addWidget(self._duplicate_button, 1)
        buttons.addWidget(self._delete_button)

        edit_buttons = QHBoxLayout()
        edit_buttons.setSpacing(8)
        edit_buttons.addWidget(self._bounds_button, 1)
        edit_buttons.addWidget(self._split_button, 1)
        edit_buttons.addWidget(self._original_button, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._columns_header)
        layout.addWidget(self._list_widget, 1)
        layout.addWidget(self._empty_label, 1)
        layout.addLayout(buttons)
        layout.addLayout(edit_buttons)
        layout.addWidget(self._processing_button)
        return layout

    def set_theme(self, theme: Theme) -> None:
        """Répercute le thème sur le dessin des lignes (le reste passe par la feuille de style)."""
        self._delegate.set_theme(theme)
        self._list_widget.viewport().update()

    # --- API publique ------------------------------------------------------

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

    # --- Comparaison avant / après traitement -----------------------------------------------------

    @property
    def plays_original(self) -> bool:
        """Vrai quand « Original » est enfoncé : les lectures utilisent l'audio brut, sans traitement."""
        return self._original_button.isChecked()

    def playback_path(self, sequence) -> str:
        """Fichier à lire pour une séquence : la version traitée, ou l'original si la comparaison A/B est active."""
        return sequence.audio_path if self.plays_original else sequence.effective_audio_path

    # --- Édition d'une séquence existante ---------------------------------------------------------

    def retime_sequence(self, sequence_id: str, start: float, end: float) -> bool:
        """Applique de nouvelles bornes à une séquence (annulable). Retourne False si l'opération a échoué."""
        if self._project is None:
            return False
        try:
            old, new = self._with_wait_cursor(
                lambda: sequence_service.retime_sequence(self._project, self._ffmpeg_service, sequence_id, start, end)
            )
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return False
        except FFmpegExecutionError:
            QMessageBox.critical(self, "AudioCut Studio — Erreur", "Erreur lors du redécoupage de la séquence.")
            return False

        self._push_command(
            f"Ajuster les bornes de « {old.name} »",
            redo_fn=lambda: sequence_service.replace_sequences(self._project, [old.id], [new]),
            undo_fn=lambda: sequence_service.replace_sequences(self._project, [new.id], [old]),
        )
        return True

    def split_sequence_at(self, sequence_id: str, at: float) -> bool:
        """Divise une séquence en deux au temps `at` de la source (annulable). Retourne False en cas d'échec."""
        if self._project is None:
            return False
        try:
            old, parts = self._with_wait_cursor(
                lambda: sequence_service.split_sequence(self._project, self._ffmpeg_service, sequence_id, at)
            )
        except (ValueError, KeyError) as exc:
            QMessageBox.warning(self, "AudioCut Studio", str(exc))
            return False
        except FFmpegExecutionError:
            QMessageBox.critical(self, "AudioCut Studio — Erreur", "Erreur lors de la division de la séquence.")
            return False

        part_ids = [part.id for part in parts]
        self._push_command(
            f"Diviser « {old.name} »",
            redo_fn=lambda: sequence_service.replace_sequences(self._project, [old.id], parts),
            undo_fn=lambda: sequence_service.replace_sequences(self._project, part_ids, [old]),
        )
        return True

    @staticmethod
    def _with_wait_cursor(task):
        """Exécute une tâche courte (découpage FFmpeg) en affichant le curseur d'attente."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return task()
        finally:
            QApplication.restoreOverrideCursor()

    def _on_bounds_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is not None:
            self.edit_bounds_requested.emit(sequence_id)

    def _on_split_clicked(self) -> None:
        sequence_id = self._current_sequence_id()
        if sequence_id is not None:
            self.split_requested.emit(sequence_id)

    def add_sequences(self, sequences: list) -> None:
        """Rattache des séquences déjà découpées au projet, en une seule action annulable."""
        if self._project is None or not sequences:
            return
        label_text = f"« {sequences[0].name} »" if len(sequences) == 1 else f"{len(sequences)} séquences"

        def redo():
            for sequence in sequences:
                sequence_service.insert_sequence(self._project, sequence)

        def undo():
            for sequence in sequences:
                sequence_service.remove_sequence_from_list(self._project, sequence.id)

        self._push_command(f"Créer {label_text}", redo_fn=redo, undo_fn=undo)

    def select_sequence(self, sequence_id: str) -> None:
        """Sélectionne (seule) la séquence d'identifiant donné et la rend visible ; sans effet si inconnue."""
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == sequence_id:
                self._list_widget.clearSelection()
                self._list_widget.setCurrentItem(item)
                item.setSelected(True)
                self._list_widget.scrollToItem(item)
                return

    # --- Affichage ---------------------------------------------------------

    def _refresh(self) -> None:
        previous_id = self._current_sequence_id()

        self._list_widget.blockSignals(True)
        self._list_widget.clear()
        if self._project is not None:
            for sequence in sorted(self._project.sequences, key=lambda seq: seq.order):
                item = QListWidgetItem(self._fallback_text(sequence))
                item.setData(Qt.ItemDataRole.UserRole, sequence.id)
                item.setData(ROW_DATA_ROLE, self._row_data(sequence))
                item.setToolTip(self._fallback_text(sequence))
                self._list_widget.addItem(item)
                if sequence.id == previous_id:
                    self._list_widget.setCurrentItem(item)
        self._list_widget.blockSignals(False)
        self._update_header()

    @staticmethod
    def _row_data(sequence) -> SequenceRow:
        return SequenceRow(
            number=sequence.order + 1,
            name=sequence.name,
            start=format_clock(sequence.source_start, decimals=3),
            duration=format_clock(sequence.duration, decimals=2),
            processed=bool(sequence.processed_audio_path),
        )

    @staticmethod
    def _fallback_text(sequence) -> str:
        """Texte brut de la ligne : infobulle, recherche au clavier et accessibilité."""
        status = " [traité]" if sequence.processed_audio_path else ""
        return (
            f"{sequence.order + 1}. {sequence.name}   "
            f"{format_timecode(sequence.source_start)} → {format_timecode(sequence.source_end)}   "
            f"({format_timecode(sequence.duration)}){status}"
        )

    def _update_header(self) -> None:
        """Compteur « Séquences (8) » et message d'accueil quand la liste est vide."""
        count = self._list_widget.count()
        self._count_label.setText(f"Séquences ({count})" if count else "Séquences")
        self._empty_label.setVisible(count == 0)
        self._list_widget.setVisible(count > 0)
        self._columns_header.setVisible(count > 0)

    def refresh(self) -> None:
        """Rafraîchit l'affichage (ex. après un traitement audio appliqué en externe)."""
        self._refresh()

    # --- Undo / redo -------------------------------------------------------

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

    # --- Accès aux séquences ----------------------------------------------

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

    def _on_current_item_changed(self, current, _previous) -> None:
        if current is None:
            return
        self.sequence_selected.emit(current.data(Qt.ItemDataRole.UserRole))

    # --- Actions -----------------------------------------------------------

    def play_sequence(self, sequence_id: str) -> None:
        """Sélectionne la séquence puis demande sa lecture (double-clic, bouton Lire)."""
        self.select_sequence(sequence_id)
        sequence = self.get_sequence(sequence_id)
        if sequence is not None:
            self.play_requested.emit(sequence.name, self.playback_path(sequence), sequence.source_start)

    def _on_item_double_clicked(self, item) -> None:
        self.play_sequence(item.data(Qt.ItemDataRole.UserRole))

    def _on_play_clicked(self) -> None:
        sequence = self.current_sequence()
        if sequence is None:
            return
        self.play_requested.emit(sequence.name, self.playback_path(sequence), sequence.source_start)

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

        label_text = f"« {duplicates[0].name} »" if len(duplicates) == 1 else f"{len(duplicates)} séquences"

        def redo():
            for duplicate in duplicates:
                sequence_service.insert_sequence(self._project, duplicate)

        def undo():
            for duplicate in duplicates:
                sequence_service.remove_sequence_from_list(self._project, duplicate.id)

        self._push_command(f"Dupliquer {label_text}", redo_fn=redo, undo_fn=undo)

    def _on_delete_clicked(self) -> None:
        if self._project is None:
            return
        targets = self.selected_sequences()
        if not targets:
            return
        # Position d'origine de chaque séquence, pour la restaurer exactement à l'annulation.
        positions = [(seq, self._project.sequences.index(seq)) for seq in targets]

        label_text = f"« {targets[0].name} »" if len(targets) == 1 else f"{len(targets)} séquences"

        def redo():
            for seq, _index in positions:
                sequence_service.remove_sequence_from_list(self._project, seq.id)

        def undo():
            for seq, index in sorted(positions, key=lambda pair: pair[1]):
                sequence_service.insert_sequence(self._project, seq, index)

        self._push_command(f"Supprimer {label_text}", redo_fn=redo, undo_fn=undo)

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
