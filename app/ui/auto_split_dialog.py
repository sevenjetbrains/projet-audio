"""Dialogue de réglage du découpage automatique en séquences selon les silences."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout

from app.services.sequence_service import AutoSplitParams


class AutoSplitDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Découpage automatique")
        defaults = AutoSplitParams()

        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(-80.0, -5.0)
        self._threshold_spin.setSuffix(" dB")
        self._threshold_spin.setValue(defaults.threshold_db)

        self._min_silence_spin = self._seconds_spin(0.1, 10.0, defaults.min_silence)
        self._padding_spin = self._seconds_spin(0.0, 2.0, defaults.keep_padding)
        self._min_segment_spin = self._seconds_spin(0.0, 60.0, defaults.min_segment)

        form = QFormLayout()
        form.addRow("Seuil de silence :", self._threshold_spin)
        form.addRow("Durée min. d'un silence :", self._min_silence_spin)
        form.addRow("Marge conservée :", self._padding_spin)
        form.addRow("Durée min. d'une séquence :", self._min_segment_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Crée une séquence pour chaque passage entre deux silences."))
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    @staticmethod
    def _seconds_spin(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(0.1)
        spin.setSuffix(" s")
        spin.setValue(value)
        return spin

    def params(self) -> AutoSplitParams:
        return AutoSplitParams(
            threshold_db=self._threshold_spin.value(),
            min_silence=self._min_silence_spin.value(),
            keep_padding=self._padding_spin.value(),
            min_segment=self._min_segment_spin.value(),
        )
