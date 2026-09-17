"""Tests de FFmpegService.detect_silences et concat_with_crossfade."""

import wave

import numpy as np
import pytest

from app.services.ffmpeg_service import FFmpegService


@pytest.fixture
def silence_then_tone_wav(tmp_path):
    """1s de silence puis 1s de tonalité forte, WAV mono 16-bit 8kHz."""
    framerate = 8000
    silence = np.zeros(framerate, dtype=np.int16)
    t = np.linspace(0, 1, framerate, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)
    samples = np.concatenate([silence, tone])

    path = tmp_path / "silence_then_tone.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(framerate)
        wav_file.writeframes(samples.tobytes())

    return str(path)


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def test_detect_silences_finds_leading_silence(ffmpeg_binaries, silence_then_tone_wav):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    silences = service.detect_silences(silence_then_tone_wav, threshold_db=-35.0, min_duration=0.3)

    assert len(silences) == 1
    start, end = silences[0]
    assert start == pytest.approx(0.0, abs=0.05)
    assert end == pytest.approx(1.0, abs=0.05)


def test_concat_with_crossfade_single_input_copies(ffmpeg_binaries, synthetic_wav_file, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_path = tmp_path / "out.wav"

    service.concat_with_crossfade([synthetic_wav_file], str(out_path), crossfade_duration=0.5)

    assert out_path.exists()


def test_concat_with_crossfade_shortens_total_duration(ffmpeg_binaries, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    framerate = 8000
    t = np.linspace(0, 2, framerate * 2, endpoint=False)
    tone = (np.sin(2 * np.pi * 440 * t) * 20000).astype(np.int16)

    path_a = tmp_path / "a.wav"
    path_b = tmp_path / "b.wav"
    for path in (path_a, path_b):
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(framerate)
            wav_file.writeframes(tone.tobytes())

    out_path = tmp_path / "merged.wav"
    service.concat_with_crossfade([str(path_a), str(path_b)], str(out_path), crossfade_duration=0.5)

    # Sans crossfade : 4s. Avec 0.5s de fondu croisé : 3.5s.
    assert _wav_duration(str(out_path)) == pytest.approx(3.5, abs=0.1)
