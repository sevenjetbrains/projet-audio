"""Tests de app.audio.waveform.compute_peaks."""

import wave

import numpy as np
import pytest

from app.audio.waveform import compute_peaks


@pytest.fixture
def synthetic_wav(tmp_path):
    """WAV mono 16-bit : 1s de silence puis 1s de tonalité forte amplitude."""
    framerate = 8000
    silence = np.zeros(framerate, dtype=np.int16)
    t = np.linspace(0, 1, framerate, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    samples = np.concatenate([silence, tone])

    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(framerate)
        wav_file.writeframes(samples.tobytes())

    return str(path), framerate


def test_compute_peaks_shape(synthetic_wav):
    path, _ = synthetic_wav
    peaks = compute_peaks(path, target_width=100)

    assert peaks.shape == (100, 2)
    assert np.all(peaks >= -1.0)
    assert np.all(peaks <= 1.0)


def test_compute_peaks_isolates_silence_vs_tone(synthetic_wav):
    path, _ = synthetic_wav

    silence_peaks = compute_peaks(path, target_width=10, start_time=0.0, end_time=1.0)
    tone_peaks = compute_peaks(path, target_width=10, start_time=1.0, end_time=2.0)

    silence_amplitude = np.abs(silence_peaks).max()
    tone_amplitude = np.abs(tone_peaks).max()

    assert silence_amplitude < 0.01
    assert tone_amplitude > 0.5


def test_compute_peaks_rejects_non_positive_width(synthetic_wav):
    path, _ = synthetic_wav
    with pytest.raises(ValueError):
        compute_peaks(path, target_width=0)
