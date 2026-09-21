"""Calcul asynchrone des peaks waveform : pyramide du fichier entier, puis peaks de la vue initiale."""

import logging
import wave

from PySide6.QtCore import QThread, Signal

from app.audio.waveform import PeakPyramid, compute_peaks

logger = logging.getLogger("audiocut")


class WaveformWorker(QThread):
    peaks_ready = Signal(object)
    pyramid_ready = Signal(object)  # résumé multi-résolution du fichier : les vues suivantes n'ont plus à le relire
    failed = Signal(str)

    def __init__(self, wav_path: str, target_width: int, parent=None) -> None:
        super().__init__(parent)
        self._wav_path = wav_path
        self._target_width = target_width

    def run(self) -> None:
        try:
            # Partagée entre la forme d'onde et la vue d'ensemble : le fichier n'est lu qu'une fois.
            pyramid = PeakPyramid.for_file(self._wav_path)
            peaks = pyramid.peaks(0.0, None, self._target_width)
            if peaks is None:  # fichier si court que la pyramide n'apporte rien
                peaks = compute_peaks(self._wav_path, self._target_width)
        except (OSError, ValueError, EOFError, wave.Error) as exc:  # fichier absent, tronqué ou pas un WAV
            logger.error("Échec du calcul de la waveform : %s", exc)
            self.failed.emit("Impossible d'afficher la waveform de ce fichier audio.")
            return

        self.peaks_ready.emit(peaks)
        self.pyramid_ready.emit(pyramid)
