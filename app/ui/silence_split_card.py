"""Carte « Découpage par silences » : réglages de détection et lancement du découpage.

Les réglages sont les mêmes que ceux d'`AutoSplitDialog` : les deux chemins
produisent un `AutoSplitParams` et passent par la même méthode de la fenêtre.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.services.sequence_service import AutoSplitParams
from app.ui.design import card_layout, label, section_label

# (clé du paramètre, libellé de colonne, minimum, maximum, suffixe)
_FIELDS = (
    ("threshold_db", "Seuil", -80.0, -5.0, " dB"),
    ("min_silence", "Silence min.", 0.1, 10.0, " s"),
    ("keep_padding", "Marge", 0.0, 2.0, " s"),
    ("min_segment", "Séquence min.", 0.0, 60.0, " s"),
)


class SilenceSplitCard(QWidget):
    """Réglages de découpage automatique posés directement dans la fenêtre principale."""

    split_requested = Signal(AutoSplitParams)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        defaults = AutoSplitParams()

        self._spins: dict[str, QDoubleSpinBox] = {}
        for key, _title, minimum, maximum, suffix in _FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(1.0 if suffix == " dB" else 0.05)
            spin.setDecimals(0 if suffix == " dB" else 2)
            spin.setSuffix(suffix)
            spin.setValue(getattr(defaults, key))
            spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            self._spins[key] = spin

        self._detected_label = label("Réglez le seuil puis lancez la détection.", "hintLabel")
        self._detected_label.setWordWrap(True)
        self._detected_label.setMinimumWidth(1)

        self.split_button = QPushButton("Découper")
        self.split_button.setToolTip("Créer une séquence pour chaque passage entre deux silences")
        self.split_button.clicked.connect(lambda: self.split_requested.emit(self.params()))

        self.setLayout(self._build_layout())

    def _build_layout(self) -> QVBoxLayout:
        frame, frame_layout = card_layout(spacing=10, margin=14)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(label("Découpage par silences", "titleLabel"))
        title_row.addWidget(self._detected_label, 1)
        title_row.addWidget(self.split_button)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(10)
        for key, title, _minimum, _maximum, _suffix in _FIELDS:
            column = QVBoxLayout()
            column.setSpacing(4)
            column.addWidget(section_label(title))
            column.addWidget(self._spins[key])
            fields_row.addLayout(column, 1)

        frame_layout.addLayout(title_row)
        frame_layout.addLayout(fields_row)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)
        return layout

    def params(self) -> AutoSplitParams:
        return AutoSplitParams(**{key: spin.value() for key, spin in self._spins.items()})

    def set_detected_count(self, count: int) -> None:
        """Résultat du dernier découpage, affiché sous le titre de la carte."""
        if count <= 0:
            self._detected_label.setText("Aucun passage détecté avec ces réglages.")
            return
        plural = "s" if count > 1 else ""
        self._detected_label.setText(f"{count} séquence{plural} détectée{plural}")
