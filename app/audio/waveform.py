"""Calcul des peaks (min/max) d'un fichier WAV pour affichage waveform.

Lit le fichier par blocs via le module stdlib `wave` (accès direct par
`setpos`), sans jamais charger l'intégralité du fichier en mémoire (§40).
"""

import wave

import numpy as np

_CHUNK_FRAMES = 65536


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
        channels = wav_file.getnchannels()
        sampwidth = wav_file.getsampwidth()
        total_frames = wav_file.getnframes()

        if sampwidth != 2:
            raise ValueError(f"Only 16-bit PCM WAV is supported (got sampwidth={sampwidth})")

        start_frame = max(0, int(start_time * framerate))
        end_frame = total_frames if end_time is None else min(total_frames, int(end_time * framerate))
        end_frame = max(end_frame, start_frame)
        range_frames = end_frame - start_frame

        peaks_min = np.full(target_width, np.inf, dtype=np.float32)
        peaks_max = np.full(target_width, -np.inf, dtype=np.float32)

        if range_frames <= 0:
            return np.zeros((target_width, 2), dtype=np.float32)

        samples_per_column = max(range_frames / target_width, 1e-9)

        wav_file.setpos(start_frame)
        frames_consumed = 0

        while frames_consumed < range_frames:
            frames_to_read = min(_CHUNK_FRAMES, range_frames - frames_consumed)
            raw = wav_file.readframes(frames_to_read)
            if not raw:
                break

            samples = np.frombuffer(raw, dtype=np.int16)
            n_frames_read = len(samples) // channels
            if n_frames_read == 0:
                break
            samples = samples[: n_frames_read * channels].reshape(n_frames_read, channels)
            mono = samples.mean(axis=1)

            global_positions = frames_consumed + np.arange(n_frames_read)
            col_indices = np.minimum(
                (global_positions / samples_per_column).astype(np.int64), target_width - 1
            )

            np.minimum.at(peaks_min, col_indices, mono)
            np.maximum.at(peaks_max, col_indices, mono)

            frames_consumed += n_frames_read

    untouched = np.isinf(peaks_min)
    peaks_min[untouched] = 0.0
    peaks_max[untouched] = 0.0

    return np.stack([peaks_min, peaks_max], axis=1) / 32768.0
