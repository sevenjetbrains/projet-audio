"""Carte « SÉQUENCE SÉLECTIONNÉE » de la disposition B.

La colonne des séquences n'est plus à côté du bloc SOURCE dans cette disposition :
cette carte rappelle, du côté de la source, ce que la liste met en avant — son nom,
ses bornes dans la vidéo d'origine et l'état de son audio.
"""

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from app.models.sequence import Sequence
from app.ui.design import card_layout, label
from app.utils.time_utils import format_clock

_EMPTY_TITLE = "Aucune séquence sélectionnée"
_EMPTY_HINT = "Choisissez une séquence dans la liste, à gauche."


class SelectedSequenceCard(QWidget):
    """Résumé en lecture seule de la séquence courante (nom, bornes, état de l'audio)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._name_label = label(_EMPTY_TITLE, "titleLabel")
        self._name_label.setWordWrap(True)
        self._start_label = label("", "valueLabel")
        self._end_label = label("", "valueLabel")
        self._state_label = label(_EMPTY_HINT, "hintLabel")
        self._state_label.setWordWrap(True)
        self._state_label.setMinimumWidth(1)

        self.setLayout(self._build_layout())
        self.set_sequence(None)

    def _build_layout(self) -> QVBoxLayout:
        frame, frame_layout = card_layout(spacing=6, margin=14)

        bounds = QHBoxLayout()
        bounds.setContentsMargins(0, 0, 0, 0)
        bounds.addWidget(self._start_label)
        bounds.addStretch(1)
        bounds.addWidget(self._end_label)

        frame_layout.addWidget(self._name_label)
        frame_layout.addLayout(bounds)
        frame_layout.addWidget(self._state_label)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(frame)
        return layout

    def set_sequence(self, sequence: Sequence | None) -> None:
        """Renseigne la carte, ou la remet à son état vide si aucune séquence n'est sélectionnée."""
        if sequence is None:
            self._name_label.setText(_EMPTY_TITLE)
            self._start_label.setText("")
            self._end_label.setText("")
            self._state_label.setText(_EMPTY_HINT)
            return
        self._name_label.setText(sequence.name)
        self._start_label.setText(format_clock(sequence.source_start))
        self._end_label.setText(format_clock(sequence.source_end))
        # Le profil de traitement n'est pas mémorisé dans la séquence : on annonce ce qui est vérifiable,
        # c'est-à-dire l'existence (ou non) d'un fichier audio traité.
        state = "son traité" if sequence.processed_audio_path else "son brut conservé"
        self._state_label.setText(f"durée {format_clock(sequence.duration)} · {state}")
