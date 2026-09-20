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
    listen_requested = Signal()
    loop_toggled = Signal(bool)
    edit_cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._editing_name: str | None = None
        self.start_spin = TimecodeSpinBox()
        self.end_spin = TimecodeSpinBox()
        self._duration_label = label(f"durée {format_clock(0.0)}", "mutedLabel")

        self._mark_start_button = self._mark_button("Début", "I", self.mark_start_requested)
        self._mark_end_button = self._mark_button("Fin", "O", self.mark_end_requested)

        self.listen_button = QPushButton("Écouter")
        self.listen_button.setToolTip("Écouter uniquement la sélection, puis s'arrêter (Maj+Espace)")
        self.listen_button.clicked.connect(self.listen_requested.emit)

        self.loop_button = QPushButton("Boucle")
        self.loop_button.setCheckable(True)
        self.loop_button.setToolTip("Répéter la sélection en boucle pour régler les bornes (L)")
        self.loop_button.toggled.connect(self.loop_toggled.emit)

        self.create_button = accent_button("Créer la séquence")
        self.create_button.clicked.connect(self.create_requested.emit)
        # La touche Entrée est câblée par la fenêtre (deux QShortcut : Return et Enter du pavé).
        self.create_button.setToolTip("Créer une séquence depuis la sélection (Entrée)")

        self.cancel_edit_button = QPushButton("Annuler")
        self.cancel_edit_button.setToolTip("Abandonner l'ajustement des bornes")
        self.cancel_edit_button.clicked.connect(self.edit_cancelled.emit)
        self.cancel_edit_button.hide()
        self._editing_label = label("", "hintLabel")
        self._editing_label.hide()

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

        self._hint_label = label(_HINT, "hintLabel")
        self._hint_label.setWordWrap(True)
        self._hint_label.setMinimumWidth(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._hint_label, 1)
        actions.addWidget(self.listen_button)
        actions.addWidget(self.loop_button)
        actions.addWidget(self._mark_start_button)
        actions.addWidget(self._mark_end_button)
        actions.addWidget(self.cancel_edit_button)
        actions.addWidget(self.create_button)

        frame_layout.addWidget(self._editing_label)
        frame_layout.addLayout(fields)
        frame_layout.addLayout(actions)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)
        return layout

    @property
    def is_editing(self) -> bool:
        return self._editing_name is not None

    def set_editing(self, name: str | None) -> None:
        """Mode « ajustement des bornes » d'une séquence existante (None pour revenir à la création)."""
        self._editing_name = name
        editing = name is not None
        self.create_button.setText(f"Mettre à jour « {name} »" if editing else "Créer la séquence")
        self.create_button.setToolTip(
            "Appliquer ces bornes à la séquence (Entrée)" if editing else "Créer une séquence depuis la sélection (Entrée)"
        )
        self.cancel_edit_button.setVisible(editing)
        self._editing_label.setVisible(editing)
        # Les boutons prennent alors toute la largeur : l'aide courte serait écrasée en une colonne de caractères.
        self._hint_label.setVisible(not editing)
        self._editing_label.setText(f"Ajustement des bornes de « {name} » : tirez les poignées sur la waveform." if editing else "")

    def refresh_duration(self) -> None:
        """Met à jour l'affichage « durée … » (à appeler si les champs changent signaux bloqués)."""
        span = max(self.end_spin.value() - self.start_spin.value(), 0.0)
        self._duration_label.setText(f"durée {format_clock(span)}")
        self.listen_button.setEnabled(span > 0)  # rien à écouter tant qu'aucune plage n'est choisie

    def set_range(self, maximum: float) -> None:
        """Borne haute des deux champs (durée de l'audio source)."""
        for spin in (self.start_spin, self.end_spin):
            spin.blockSignals(True)
            spin.setRange(0.0, maximum)
            spin.blockSignals(False)
        self.refresh_duration()
