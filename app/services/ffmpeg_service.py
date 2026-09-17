"""Exécution centralisée des commandes FFmpeg.

Toutes les opérations FFmpeg de l'application passent par cette classe
(§8 du spec : ne pas disperser les appels subprocess). Les méthodes sont
bloquantes et en pur Python — ce sont les workers (app/workers/) qui les
rendent asynchrones pour ne pas geler l'interface Qt.
"""

import re
import subprocess
from collections.abc import Callable

_TIME_PATTERN = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


class FFmpegExecutionError(RuntimeError):
    """Levée quand une commande FFmpeg échoue (détail technique dans l'exception)."""


class FFmpegService:
    def __init__(self, ffmpeg_path: str) -> None:
        self._ffmpeg_path = ffmpeg_path

    def extract_audio(
        self,
        video_path: str,
        out_wav_path: str,
        total_duration: float,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        """Extrait la piste audio complète d'une vidéo en WAV PCM, sans toucher au fichier source."""
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            out_wav_path,
        ]

        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        stderr_lines: list[str] = []
        assert process.stderr is not None
        for line in process.stderr:
            stderr_lines.append(line)
            match = _TIME_PATTERN.search(line)
            if match and on_progress and total_duration > 0:
                hours, minutes, seconds = match.groups()
                elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                on_progress(min(elapsed / total_duration, 1.0))

        process.wait()

        if process.returncode != 0:
            technical_detail = "".join(stderr_lines[-20:])
            raise FFmpegExecutionError(technical_detail)

        if on_progress:
            on_progress(1.0)
