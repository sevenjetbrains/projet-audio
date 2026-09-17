"""Tests de FFmpegService.extract_audio."""

import wave

import pytest

from app.services.ffmpeg_service import FFmpegExecutionError, FFmpegService
from app.services.ffprobe_service import FFprobeService


def test_extract_audio_produces_valid_wav(ffmpeg_binaries, sample_video, tmp_path):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_wav = tmp_path / "source.wav"

    progress_values: list[float] = []
    ffmpeg_service.extract_audio(
        sample_video, str(out_wav), media_info.duration, on_progress=progress_values.append
    )

    assert out_wav.exists()
    assert out_wav.stat().st_size > 0

    with wave.open(str(out_wav), "rb") as wav_file:
        wav_duration = wav_file.getnframes() / wav_file.getframerate()
    assert wav_duration == pytest.approx(media_info.duration, abs=0.2)

    assert progress_values
    assert progress_values[-1] == pytest.approx(1.0)
    assert progress_values == sorted(progress_values)


def test_extract_audio_invalid_source_raises(ffmpeg_binaries, tmp_path):
    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_wav = tmp_path / "source.wav"

    with pytest.raises(FFmpegExecutionError):
        ffmpeg_service.extract_audio("this_file_does_not_exist.mp4", str(out_wav), 1.0)
