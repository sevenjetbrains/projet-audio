"""Aperçu des passages à transformer en séquences : on coche ceux à garder.

Sert au découpage automatique (passages entre silences) comme au découpage aux repères.
Une entrée est `(début, fin)` ou `(début, fin, nom)` : dès qu'un nom est donné, une colonne
« Nom » s'ajoute pour montrer comment les séquences s'appelleront."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.screen_fit import ScreenFittedDialog
from app.utils.time_utils import format_timecode

_COLUMNS = ("", "N°", "Début", "Fin", "Durée")
_NAME_COLUMN = "Nom"


class SplitPreviewDialog(ScreenFittedDialog):
    PREFERRED_SIZE = (520, 420)
    MINIMUM_SIZE = (360, 280)

    def __init__(self, ranges: list[tuple], parent=None, title: str = "Passages détectés") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._ranges = list(ranges)

        named = any(len(entry) > 2 and entry[2] for entry in self._ranges)
        columns = (*_COLUMNS, _NAME_COLUMN) if named else _COLUMNS
        self._table = QTableWidget(len(self._ranges), len(columns))
        self._table.setHorizontalHeaderLabels(list(columns))
        self._table.verticalHeader().hide()
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 32)
        self._table.setColumnWidth(1, 44)
        for row, entry in enumerate(self._ranges):
            start, end = entry[0], entry[1]
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Checked)
            self._table.setItem(row, 0, check)
            cells = [str(row + 1), format_timecode(start), format_timecode(end), format_timecode(end - start)]
            if named:
                cells.append(entry[2] if len(entry) > 2 else "")
            for column, text in enumerate(cells, start=1):
                self._table.setItem(row, column, QTableWidgetItem(text))
        self._table.itemChanged.connect(lambda _item: self._update_summary())

        select_all = QPushButton("Tout cocher")
        select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        select_none = QPushButton("Tout décocher")
        select_none.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        tools = QHBoxLayout()
        tools.addWidget(select_all)
        tools.addWidget(select_none)
        tools.addStretch(1)

        self._summary = QLabel()
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Créer les séquences")
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Décochez les passages à ignorer avant de créer les séquences."))
        layout.addLayout(tools)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._summary)
        layout.addWidget(self._buttons)
        self._update_summary()

    def _set_all(self, state: Qt.CheckState) -> None:
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(state)

    def selected_ranges(self) -> list[tuple]:
        """Passages cochés, dans l'ordre chronologique."""
        return [
            self._ranges[row]
            for row in range(self._table.rowCount())
            if self._table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]

    def _update_summary(self) -> None:
        selected = self.selected_ranges()
        total = sum(entry[1] - entry[0] for entry in selected)
        self._summary.setText(f"{len(selected)} sur {len(self._ranges)} sélectionnés — durée totale {format_timecode(total)}")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(selected))
