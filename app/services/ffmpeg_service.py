"""Exécution centralisée des commandes FFmpeg.

Toutes les opérations FFmpeg de l'application passent par cette classe
(§8 du spec : ne pas disperser les appels subprocess). Les méthodes sont
bloquantes et en pur Python — ce sont les workers (app/workers/) qui les
rendent asynchrones pour ne pas geler l'interface Qt.
"""

import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

from app.utils.progress import sub_progress

_TIME_PATTERN = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
_VERSION_PATTERN = re.compile(r"ffmpeg version n?(\d+(?:\.\d+)*)")
_MAX_VOLUME_PATTERN = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB")
_SILENCE_START_PATTERN = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_SILENCE_END_PATTERN = re.compile(r"silence_end:\s*(-?\d+\.?\d*)")

_MP3_BITRATES = {"128", "192", "256", "320"}
_WAV_SAMPLE_FORMATS = {"16": "pcm_s16le", "24": "pcm_s24le"}
_FLAC_SAMPLE_FORMATS = {"16": "s16", "24": "s32"}
_AAC_BITRATES = {"128", "192", "256", "320"}
_OGG_QUALITIES = {"3", "5", "7"}
_OPUS_BITRATES = {"64", "96", "128", "192"}


def wav_duration(path: str) -> float:
    """Durée d'un WAV en secondes (0.0 si illisible : la progression est alors simplement non affichée)."""
    try:
        with wave.open(path, "rb") as wav_file:
            return wav_file.getnframes() / wav_file.getframerate()
    except (wave.Error, EOFError, OSError, ZeroDivisionError):
        return 0.0


class FFmpegExecutionError(RuntimeError):
    """Levée quand une commande FFmpeg échoue (détail technique dans l'exception)."""


class FFmpegCancelled(RuntimeError):
    """Levée quand l'appelant a demandé l'arrêt : le processus a été interrompu, pas planté.

    Distincte de `FFmpegExecutionError` pour que l'interface ne présente pas une annulation
    volontaire comme une erreur.
    """


class FFmpegService:
    def __init__(self, ffmpeg_path: str) -> None:
        self._ffmpeg_path = ffmpeg_path

    def version(self) -> str:
        """Numéro de version de FFmpeg (« 7.1 »), ou chaîne vide s'il est illisible.

        Les binaires distribués suffixent leur version (`7.1-full_build-www.gyan.dev`) :
        seule la partie numérique est retenue, c'est la seule utile à afficher."""
        try:
            output = subprocess.run(
                [self._ffmpeg_path, "-version"], capture_output=True, text=True, timeout=5
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
        match = _VERSION_PATTERN.match(output)
        return match.group(1) if match else ""

    def measure_peak_db(self, audio_path: str) -> float:
        """Crête du fichier en dBFS (0 = pleine échelle), mesurée par `volumedetect`.

        Retourne 0.0 si la mesure échoue : la normalisation par crête n'appliquera alors
        qu'une atténuation vers la cible, jamais une amplification à l'aveugle."""
        cmd = [self._ffmpeg_path, "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"]
        try:
            lines = self._run(cmd)
        except FFmpegExecutionError:
            return 0.0
        match = _MAX_VOLUME_PATTERN.search("".join(lines))
        return float(match.group(1)) if match else 0.0

    def extract_audio(
        self,
        video_path: str,
        out_wav_path: str,
        total_duration: float,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        """Extrait la piste audio complète d'une vidéo en WAV PCM, sans toucher au fichier source.

        `should_cancel` est consulté au fil de la progression : dès qu'il répond vrai, le
        processus est interrompu et `FFmpegCancelled` est levée (l'extraction d'une longue
        vidéo est la seule opération assez lente pour qu'on veuille y renoncer)."""
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            out_wav_path,
        ]
        self._run(cmd, total_duration=total_duration, on_progress=on_progress, should_cancel=should_cancel)

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

    def concat_audio(
        self, input_wav_paths: list[str], out_wav_path: str, on_progress: Callable[[float], None] | None = None
    ) -> None:
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
            total = sum(wav_duration(path) for path in input_wav_paths)
            self._run(cmd, total_duration=total, on_progress=on_progress)
        finally:
            Path(filelist_path).unlink(missing_ok=True)

    def detect_silences(
        self, source_wav_path: str, threshold_db: float, min_duration: float
    ) -> list[tuple[float, float]]:
        """Détecte les silences via le filtre `silencedetect` (aucun fichier de sortie produit)."""
        cmd = [
            self._ffmpeg_path,
            "-i", source_wav_path,
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null",
            "-",
        ]
        stderr_lines = self._run(cmd)

        silences: list[tuple[float, float]] = []
        pending_start: float | None = None
        for line in stderr_lines:
            start_match = _SILENCE_START_PATTERN.search(line)
            if start_match:
                pending_start = float(start_match.group(1))
                continue
            end_match = _SILENCE_END_PATTERN.search(line)
            if end_match and pending_start is not None:
                silences.append((pending_start, float(end_match.group(1))))
                pending_start = None

        return silences

    def concat_with_crossfade(
        self,
        input_wav_paths: list[str],
        out_wav_path: str,
        crossfade_duration: float,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        """Concatène plusieurs WAV avec un fondu croisé de `crossfade_duration` secondes entre chacun."""
        if not input_wav_paths:
            raise ValueError("input_wav_paths must not be empty")

        if len(input_wav_paths) == 1:
            shutil.copyfile(input_wav_paths[0], out_wav_path)
            if on_progress:
                on_progress(1.0)
            return

        intermediates: list[str] = []
        try:
            current = input_wav_paths[0]
            remaining = input_wav_paths[1:]
            for index, next_path in enumerate(remaining):
                is_last = index == len(remaining) - 1
                if is_last:
                    out = out_wav_path
                else:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        out = tmp.name
                    intermediates.append(out)

                cmd = [
                    self._ffmpeg_path,
                    "-y",
                    "-i", current,
                    "-i", next_path,
                    "-filter_complex", f"acrossfade=d={crossfade_duration}:c1=tri:c2=tri",
                    out,
                ]
                step_total = wav_duration(current) + wav_duration(next_path) - crossfade_duration
                self._run(
                    cmd,
                    total_duration=step_total,
                    on_progress=sub_progress(on_progress, index / len(remaining), (index + 1) / len(remaining)),
                )
                current = out
        finally:
            for path in intermediates:
                Path(path).unlink(missing_ok=True)

    def apply_filters(
        self,
        source_wav_path: str,
        out_wav_path: str,
        filter_chain: str,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        """Applique une chaîne de filtres audio FFmpeg (`-af`), sans toucher au fichier source."""
        cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-af", filter_chain, out_wav_path]
        self._run(
            cmd,
            total_duration=wav_duration(source_wav_path),
            on_progress=on_progress,
            should_cancel=should_cancel,
        )

    def export_audio(
        self,
        source_wav_path: str,
        out_path: str,
        fmt: str,
        quality: str,
        on_progress: Callable[[float], None] | None = None,
        sample_rate: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        """Réencode un WAV source vers le format/qualité d'export choisis par l'utilisateur.

        `sample_rate` rééchantillonne la sortie (48 000 Hz par exemple) ; sans lui, la fréquence
        de la source est conservée. `should_cancel` interrompt l'encodage en cours."""
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
        elif fmt == "flac":
            sample_format = _FLAC_SAMPLE_FORMATS.get(quality)
            if sample_format is None:
                raise ValueError(f"Qualité FLAC non supportée : {quality}")
            cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-codec:a", "flac", "-sample_fmt", sample_format, out_path]
        elif fmt == "m4a":
            if quality not in _AAC_BITRATES:
                raise ValueError(f"Débit AAC non supporté : {quality}")
            cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-codec:a", "aac", "-b:a", f"{quality}k", out_path]
        elif fmt == "ogg":
            if quality not in _OGG_QUALITIES:
                raise ValueError(f"Qualité OGG non supportée : {quality}")
            cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-codec:a", "libvorbis", "-q:a", quality, out_path]
        elif fmt == "opus":
            if quality not in _OPUS_BITRATES:
                raise ValueError(f"Débit Opus non supporté : {quality}")
            cmd = [self._ffmpeg_path, "-y", "-i", source_wav_path, "-codec:a", "libopus", "-b:a", f"{quality}k", out_path]
        else:
            raise ValueError(f"Format d'export non supporté : {fmt}")

        if sample_rate:
            cmd[-1:-1] = ["-ar", str(sample_rate)]  # avant le fichier de sortie, comme toute option d'encodage
        self._run(
            cmd,
            total_duration=wav_duration(source_wav_path),
            on_progress=on_progress,
            should_cancel=should_cancel,
        )

    def create_preview_proxy(
        self,
        source_video_path: str,
        out_path: str,
        total_duration: float,
        height: int,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        """Encode une copie réduite à image clé très rapprochée (déplacements instantanés dans l'aperçu).

        Écrite dans un fichier temporaire puis renommée : un aperçu à moitié écrit (arrêt, plantage) ne peut
        jamais être pris pour une copie complète.
        """
        partial = out_path + ".part.mp4"
        cmd = [
            self._ffmpeg_path, "-y", "-i", source_video_path,
            "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
            "-g", "6", "-keyint_min", "6", "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
            partial,
        ]
        try:
            self._run(cmd, total_duration=total_duration, on_progress=on_progress)
            Path(partial).replace(out_path)
        finally:
            Path(partial).unlink(missing_ok=True)

    def _run(
        self,
        cmd: list[str],
        total_duration: float = 0.0,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> list[str]:
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
            if should_cancel is not None and should_cancel():
                process.terminate()
                process.wait()
                raise FFmpegCancelled("Opération annulée.")
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

        return stderr_lines
