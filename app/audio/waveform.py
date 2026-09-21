"""Calcul des peaks (min/max) d'un fichier WAV pour affichage waveform.

Lit le fichier par blocs via le module stdlib `wave` (accès direct par
`setpos`), sans jamais charger l'intégralité du fichier en mémoire (§40).

Deux niveaux d'outils :
- `compute_peaks` lit le fichier (vectorisé) : adapté à une plage courte ou à un calcul unique en tâche de fond ;
- `PeakPyramid` résume le fichier entier une fois pour toutes en min/max à plusieurs résolutions, ce qui rend
  n'importe quelle vue (redimensionnement, zoom, défilement) instantanée. Sur 26 minutes d'audio, relire le
  fichier à chaque événement de redimensionnement prenait de 9 à 47 secondes et figeait l'interface.
"""

import threading
import wave
from pathlib import Path

import numpy as np

_CHUNK_FRAMES = 1 << 20  # ~1 million de trames par lecture : peu d'appels Python, mémoire bornée


def _read_mono_chunks(wav_file: wave.Wave_read, frames: int, chunk_frames: int = _CHUNK_FRAMES):
    """Produit (décalage, échantillons mono float32) pour `frames` trames à partir de la position courante."""
    channels = wav_file.getnchannels()
    consumed = 0
    while consumed < frames:
        raw = wav_file.readframes(min(chunk_frames, frames - consumed))
        if not raw:
            break
        samples = np.frombuffer(raw, dtype=np.int16)
        count = len(samples) // channels
        if count == 0:
            break
        samples = samples[: count * channels]
        mono = samples.astype(np.float32) if channels == 1 else samples.reshape(count, channels).mean(axis=1, dtype=np.float32)
        yield consumed, mono
        consumed += count


def compute_peaks(
    wav_path: str,
    target_width: int,
    start_time: float = 0.0,
    end_time: float | None = None,
) -> np.ndarray:
    """Retourne un tableau (target_width, 2) de min/max normalisés dans [-1, 1]."""
    if target_width <= 0:
        raise ValueError("target_width must be positive")

    with wave.open(wav_path, "rb") as wav_file:
        framerate = wav_file.getframerate()
        sampwidth = wav_file.getsampwidth()
        total_frames = wav_file.getnframes()

        if sampwidth != 2:
            raise ValueError(f"Only 16-bit PCM WAV is supported (got sampwidth={sampwidth})")

        start_frame = max(0, int(start_time * framerate))
        end_frame = total_frames if end_time is None else min(total_frames, int(end_time * framerate))
        end_frame = max(end_frame, start_frame)
        range_frames = end_frame - start_frame

        if range_frames <= 0:
            return np.zeros((target_width, 2), dtype=np.float32)

        peaks_min = np.full(target_width, np.inf, dtype=np.float32)
        peaks_max = np.full(target_width, -np.inf, dtype=np.float32)
        samples_per_column = max(range_frames / target_width, 1e-9)

        wav_file.setpos(start_frame)
        for offset, mono in _read_mono_chunks(wav_file, range_frames):
            count = len(mono)
            if samples_per_column < 1.0:
                # Plus de colonnes que de trames : chaque trame tient dans sa propre colonne, sans regroupement.
                columns = np.minimum(((offset + np.arange(count)) / samples_per_column).astype(np.int64), target_width - 1)
                peaks_min[columns] = np.minimum(peaks_min[columns], mono)
                peaks_max[columns] = np.maximum(peaks_max[columns], mono)
                continue

            # Colonnes touchées par ce bloc, et première trame (relative au bloc) de chacune : une réduction
            # vectorisée par colonne remplace le parcours trame par trame (np.minimum.at, très lent).
            first_col = min(int(offset / samples_per_column), target_width - 1)
            last_col = min(int((offset + count - 1) / samples_per_column), target_width - 1)
            columns = np.arange(first_col, last_col + 1)
            starts = np.ceil(columns * samples_per_column).astype(np.int64) - offset
            starts = np.clip(starts, 0, count - 1)
            starts[0] = 0
            peaks_min[first_col : last_col + 1] = np.minimum(peaks_min[first_col : last_col + 1], np.minimum.reduceat(mono, starts))
            peaks_max[first_col : last_col + 1] = np.maximum(peaks_max[first_col : last_col + 1], np.maximum.reduceat(mono, starts))

    untouched = np.isinf(peaks_min)
    peaks_min[untouched] = 0.0
    peaks_max[untouched] = 0.0

    return np.stack([peaks_min, peaks_max], axis=1) / 32768.0


# --- Pyramide de peaks -------------------------------------------------------------------------------------

_BASE_BLOCK = 64  # trames résumées par le niveau le plus fin
_LEVEL_FACTOR = 4  # chaque niveau résume 4 fois plus de trames que le précédent
_TOP_LEVEL_MAX_BLOCKS = 2048  # on s'arrête quand un niveau est assez petit


class PeakPyramid:
    """Min/max d'un WAV à plusieurs résolutions, pour afficher n'importe quelle vue sans relire le fichier."""

    def __init__(self, framerate: int, total_frames: int, levels: list[tuple[int, np.ndarray, np.ndarray]]) -> None:
        self.framerate = framerate
        self.total_frames = total_frames
        self._levels = levels  # (trames par bloc, minima, maxima), du plus fin au plus grossier

    @property
    def duration(self) -> float:
        return self.total_frames / self.framerate if self.framerate else 0.0

    @classmethod
    def build(cls, wav_path: str) -> "PeakPyramid":
        """Lit le fichier une seule fois (par blocs) et résume ses min/max à chaque résolution."""
        with wave.open(wav_path, "rb") as wav_file:
            framerate = wav_file.getframerate()
            total_frames = wav_file.getnframes()
            if wav_file.getsampwidth() != 2:
                raise ValueError(f"Only 16-bit PCM WAV is supported (got sampwidth={wav_file.getsampwidth()})")

            # Blocs de lecture alignés sur le bloc de base : chaque bloc de base est complet, sauf le dernier.
            chunk = _BASE_BLOCK * (_CHUNK_FRAMES // _BASE_BLOCK)
            mins, maxs = [], []
            for _offset, mono in _read_mono_chunks(wav_file, total_frames, chunk):
                usable = (len(mono) // _BASE_BLOCK) * _BASE_BLOCK
                if usable:
                    blocks = mono[:usable].reshape(-1, _BASE_BLOCK)
                    mins.append(blocks.min(axis=1))
                    maxs.append(blocks.max(axis=1))
                if usable < len(mono):  # dernière trame partielle
                    tail = mono[usable:]
                    mins.append(np.array([tail.min()], dtype=np.float32))
                    maxs.append(np.array([tail.max()], dtype=np.float32))

        base_min = np.concatenate(mins) if mins else np.zeros(0, dtype=np.float32)
        base_max = np.concatenate(maxs) if maxs else np.zeros(0, dtype=np.float32)
        levels = [(_BASE_BLOCK, base_min, base_max)]
        block, current_min, current_max = _BASE_BLOCK, base_min, base_max
        while len(current_min) > _TOP_LEVEL_MAX_BLOCKS:
            current_min, current_max = _coarsen(current_min, np.minimum), _coarsen(current_max, np.maximum)
            block *= _LEVEL_FACTOR
            levels.append((block, current_min, current_max))
        return cls(framerate, total_frames, levels)

    def peaks(self, start_time: float, end_time: float | None, width: int) -> np.ndarray | None:
        """(width, 2) de min/max normalisés pour la plage donnée, ou None si la plage est trop fine pour la pyramide.

        None signale à l'appelant qu'il doit lire directement le fichier (`compute_peaks`) : une plage aussi courte
        est petite, donc rapide à lire.
        """
        if width <= 0 or self.total_frames <= 0:
            return None
        start_frame = max(0, int(start_time * self.framerate))
        end_frame = self.total_frames if end_time is None else min(self.total_frames, int(end_time * self.framerate))
        if end_frame <= start_frame:
            return np.zeros((width, 2), dtype=np.float32)

        frames_per_column = (end_frame - start_frame) / width
        block, block_min, block_max = self._level_for(frames_per_column)
        if block is None:
            return None

        first = start_frame // block
        last = min(-(-end_frame // block), len(block_min))  # arrondi vers le haut
        if last <= first:
            return np.zeros((width, 2), dtype=np.float32)

        # Frontières des colonnes exprimées en blocs ; chaque colonne couvre au moins un bloc.
        edges = np.linspace(first, last, width + 1)
        starts = np.minimum(edges[:-1].astype(np.int64), last - 1)
        col_min = np.minimum.reduceat(block_min[first:last], starts - first)
        col_max = np.maximum.reduceat(block_max[first:last], starts - first)
        return np.stack([col_min, col_max], axis=1).astype(np.float32) / 32768.0

    def _level_for(self, frames_per_column: float):
        """Niveau le plus grossier dont un bloc tient dans une colonne (au moins un bloc par colonne)."""
        chosen = None
        for block, block_min, block_max in self._levels:
            if block <= frames_per_column:
                chosen = (block, block_min, block_max)
        return chosen if chosen is not None else (None, None, None)

    # --- Partage entre widgets : la pyramide d'un fichier n'est construite qu'une fois ---------------------

    _cache: "dict[tuple, PeakPyramid]" = {}
    _cache_lock = threading.Lock()

    @classmethod
    def for_file(cls, wav_path: str) -> "PeakPyramid":
        """Pyramide du fichier, construite au premier appel puis réutilisée (forme d'onde et vue d'ensemble)."""
        stat = Path(wav_path).stat()
        key = (str(Path(wav_path).resolve()), stat.st_mtime_ns, stat.st_size)
        with cls._cache_lock:
            cached = cls._cache.get(key)
            if cached is None:
                cached = cls.build(wav_path)
                if len(cls._cache) >= 3:  # quelques fichiers récents suffisent (un projet à la fois)
                    cls._cache.pop(next(iter(cls._cache)))
                cls._cache[key] = cached
            return cached


def _coarsen(values: np.ndarray, reducer) -> np.ndarray:
    """Regroupe les valeurs par paquets de _LEVEL_FACTOR (le dernier paquet peut être plus court)."""
    usable = (len(values) // _LEVEL_FACTOR) * _LEVEL_FACTOR
    grouped = reducer.reduce(values[:usable].reshape(-1, _LEVEL_FACTOR), axis=1) if usable else values[:0]
    if usable < len(values):
        grouped = np.concatenate([grouped, [reducer.reduce(values[usable:])]]).astype(values.dtype)
    return grouped
