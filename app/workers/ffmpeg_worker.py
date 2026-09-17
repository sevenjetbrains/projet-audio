"""Exécution asynchrone des opérations FFmpeg via QThread, sans bloquer l'UI."""

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.services.export_service import ExportError
from app.services.ffmpeg_service import FFmpegExecutionError, FFmpegService
from app.services.project_service import ProjectLoadError

logger = logging.getLogger("audiocut")


class ExtractAudioWorker(QThread):
    progress = Signal(int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        ffmpeg_service: FFmpegService,
        video_path: str,
        out_wav_path: str,
        total_duration: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._ffmpeg_service = ffmpeg_service
        self._video_path = video_path
        self._out_wav_path = out_wav_path
        self._total_duration = total_duration

    def run(self) -> None:
        try:
            self._ffmpeg_service.extract_audio(
                self._video_path,
                self._out_wav_path,
                self._total_duration,
                on_progress=lambda fraction: self.progress.emit(int(fraction * 100)),
            )
        except FFmpegExecutionError as exc:
            logger.error("Échec de l'extraction audio : %s", exc)
            self.failed.emit("Erreur lors du traitement audio. Consultez les logs pour plus de détails.")
            return

        self.succeeded.emit(self._out_wav_path)


class FFmpegTaskWorker(QThread):
    """Worker générique pour une opération FFmpeg sans progression fine (cut/concat/export)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[], Any], parent=None) -> None:
        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        try:
            result = self._task()
        except (ExportError, ProjectLoadError) as exc:
            self.failed.emit(str(exc))
            return
        except FFmpegExecutionError as exc:
            logger.error("Échec d'une opération FFmpeg : %s", exc)
            self.failed.emit("Erreur lors du traitement audio. Consultez les logs pour plus de détails.")
            return

        self.succeeded.emit(result)
