"""Exécution centralisée des commandes FFmpeg.

Toutes les opérations FFmpeg de l'application passent par cette classe
(§8 du spec : ne pas disperser les appels subprocess). Les méthodes sont
bloquantes et en pur Python — ce sont les workers (app/workers/) qui les
rendent asynchrones pour ne pas geler l'interface Qt.
"""

import re
import subprocess
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

_TIME_PATTERN = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

_MP3_BITRATES = {"128", "192", "256", "320"}
_WAV_SAMPLE_FORMATS = {"16": "pcm_s16le", "24": "pcm_s24le"}


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
        self._run(cmd, total_duration=total_duration, on_progress=on_progress)

    def cut_audio(self, source_wav_path: str, out_wav_path: str, start: float, end: float) -> None:
        """Découpe une plage [start, end] (secondes) d'un WAV PCM source, sans le modifier.

        Implémenté par lecture/écriture directe des frames (module stdlib `wave`)
        plutôt que via ffmpeg -ss/-t : ffmpeg produisait un léger dépassement de
        durée avec -c copy sur ce type de fichier, alors qu'une découpe PCM directe
        est exacte à l'échantillon et évite un aller-retour subprocess.
        """
        with wave.open(source_wav_path, "rb") as source:
            framerate = source.getframerate()
            start_frame = max(0, int(start * framerate))
            end_frame = min(source.getnframes(), int(end * framerate))
            n_frames = max(end_frame - start_frame, 0)
            source.setpos(start_frame)
            frames = source.readframes(n_frames)
            params = source.getparams()

        with wave.open(out_wav_path, "wb") as out:
            out.setparams(params)
            out.writeframes(frames)

    def concat_audio(self, input_wav_paths: list[str], out_wav_path: str) -> None:
        """Concatène plusieurs WAV (dans l'ordre donné) en un seul fichier, sans transition."""
        if not input_wav_paths:
            raise ValueError("input_wav_paths must not be empty")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as filelist:
            for path in input_wav_paths:
                escaped = Path(path).as_posix().replace("'", "'\\''")
                filelist.write(f"file '{escaped}'\n")
            filelist_path = filelist.name

        try:
            cmd = [
                self._ffmpeg_path,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", filelist_path,
                "-c", "copy",
                out_wav_path,
            ]
            self._run(cmd)
        finally:
            Path(filelist_path).unlink(missing_ok=True)

    def export_audio(self, source_wav_path: str, out_path: str, fmt: str, quality: str) -> None:
        """Réencode un WAV source vers le format/qualité d'export choisis par l'utilisateur."""
        fmt = fmt.lower()

        if fmt == "wav":
            sample_format = _WAV_SAMPLE_FORMATS.get(quality)
            if sample_format is None:
                raise ValueError(f"Qualité WAV non supportée : {quality}")
            cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-acodec", sample_format, out_path]
        elif fmt == "mp3":
            if quality not in _MP3_BITRATES:
                raise ValueError(f"Débit MP3 non supporté : {quality}")
            cmd = [
                self._ffmpeg_path, "-y", "-i", source_wav_path,
                "-codec:a", "libmp3lame", "-b:a", f"{quality}k",
                out_path,
            ]
        else:
            raise ValueError(f"Format d'export non supporté : {fmt}")

        self._run(cmd)

    def _run(
        self,
        cmd: list[str],
        total_duration: float = 0.0,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
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
