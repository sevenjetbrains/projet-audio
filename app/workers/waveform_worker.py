"""Calcul asynchrone des peaks waveform pour la vue initiale (fichier entier)."""

import logging

from PySide6.QtCore import QThread, Signal

from app.audio.waveform import compute_peaks

logger = logging.getLogger("audiocut")


class WaveformWorker(QThread):
    peaks_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, wav_path: str, target_width: int, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path
        self._target_width = target_width

    def run(self) -> None:
        try:
            peaks = compute_peaks(self._wav_path, self._target_width)
        except (OSError, ValueError) as exc:
            logger.error("Échec du calcul de la waveform : %s", exc)
            self.failed.emit("Impossible d'afficher la waveform de ce fichier audio.")
            return

        self.peaks_ready.emit(peaks)
