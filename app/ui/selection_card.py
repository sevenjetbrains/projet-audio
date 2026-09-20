"""Carte SÉLECTION : bornes de la plage choisie sur la waveform et création de la séquence."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.ui.design import accent_button, card_layout, label, section_label
from app.ui.timecode_spinbox import TimecodeSpinBox
from app.utils.time_utils import format_clock

_HINT = "La vidéo suit les bornes."


class SelectionCard(QWidget):
    """Bornes de sélection, marquage I/O et bouton de création, tels que dans la maquette."""

    mark_start_requested = Signal()
    mark_end_requested = Signal()
    create_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.start_spin = TimecodeSpinBox()
        self.end_spin = TimecodeSpinBox()
        self._duration_label = label(f"durée {format_clock(0.0)}", "mutedLabel")

        self._mark_start_button = self._mark_button("Début", "I", self.mark_start_requested)
        self._mark_end_button = self._mark_button("Fin", "O", self.mark_end_requested)

        self.create_button = accent_button("Créer la séquence")
        self.create_button.clicked.connect(self.create_requested.emit)
        # La touche Entrée est câblée par la fenêtre (deux QShortcut : Return et Enter du pavé).
        self.create_button.setToolTip("Créer une séquence depuis la sélection (Entrée)")

        self.setLayout(self._build_layout())
        for spin in (self.start_spin, self.end_spin):
            spin.valueChanged.connect(self.refresh_duration)
        self.refresh_duration()

    def _mark_button(self, text: str, key: str, signal) -> QWidget:
        """Bouton « Début I » / « Fin O » : le raccourci est géré par la fenêtre, pas par le bouton."""
        button = QPushButton(f"{text}  {key}")
        button.setToolTip(f"Placer la borne « {text.lower()} » à la position de lecture ({key})")
        button.clicked.connect(signal.emit)
        return button

    def _build_layout(self) -> QVBoxLayout:
        frame, frame_layout = card_layout(spacing=10, margin=14)

        fields = QHBoxLayout()
        fields.setSpacing(8)
        fields.addWidget(section_label("Sélection"))
        fields.addSpacing(6)
        fields.addWidget(label("Début", "mutedLabel"))
        fields.addWidget(self.start_spin)
        fields.addWidget(label("Fin", "mutedLabel"))
        fields.addWidget(self.end_spin)
        fields.addWidget(self._duration_label)
        fields.addStretch(1)

        hint = label(_HINT, "hintLabel")
        hint.setWordWrap(True)
        hint.setMinimumWidth(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(hint, 1)
        actions.addWidget(self._mark_start_button)
        actions.addWidget(self._mark_end_button)
        actions.addWidget(self.create_button)

        frame_layout.addLayout(fields)
        frame_layout.addLayout(actions)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)
        return layout

    def refresh_duration(self) -> None:
        """Met à jour l'affichage « durée … » (à appeler si les champs changent signaux bloqués)."""
        span = max(self.end_spin.value() - self.start_spin.value(), 0.0)
        self._duration_label.setText(f"durée {format_clock(span)}")

    def set_range(self, maximum: float) -> None:
        """Borne haute des deux champs (durée de l'audio source)."""
        for spin in (self.start_spin, self.end_spin):
            spin.blockSignals(True)
            spin.setRange(0.0, maximum)
            spin.blockSignals(False)
        self.refresh_duration()
