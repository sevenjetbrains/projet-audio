"""Champ numérique affichant des secondes sous forme de timecode `HH:MM:SS,mmm`.

Reste un QDoubleSpinBox : la valeur manipulée par le code est toujours un nombre
de secondes, seul l'affichage et la saisie passent par le timecode.
"""

import re

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QWidget

from app.utils.time_utils import format_timecode_fr, parse_timecode

# Caractères acceptés pendant une saisie encore incomplète (« 00:04: »).
_PARTIAL_PATTERN = re.compile(r"[\d:.,]*")


class TimecodeSpinBox(QDoubleSpinBox):
    """Bornes de sélection saisies et affichées en timecode (maquette : `00:04:12,340`)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDecimals(3)
        self.setSingleStep(0.1)
        self.setRange(0.0, 0.0)
        self.setProperty("timecode", "true")
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setMinimumWidth(112)

    def textFromValue(self, value: float) -> str:
        return format_timecode_fr(value)

    def valueFromText(self, text: str) -> float:
        parsed = parse_timecode(text)
        return self.value() if parsed is None else parsed

    def validate(self, text: str, position: int):
        stripped = text.strip()
        if not stripped:
            return QValidator.State.Intermediate, text, position
        if parse_timecode(text) is not None:
            return QValidator.State.Acceptable, text, position
        if _PARTIAL_PATTERN.fullmatch(stripped):
            return QValidator.State.Intermediate, text, position
        return QValidator.State.Invalid, text, position
