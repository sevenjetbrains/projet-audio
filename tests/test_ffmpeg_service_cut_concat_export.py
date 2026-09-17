"""Tests de FFmpegService.cut_audio / concat_audio / export_audio."""

import wave

import pytest

from app.services.ffmpeg_service import FFmpegExecutionError, FFmpegService
from app.services.ffprobe_service import FFprobeService


@pytest.fixture
def extracted_source_wav(ffmpeg_binaries, sample_video, tmp_path):
    """Audio complet extrait d'une vidéo de test (réutilise le pipeline Phase 2)."""
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_wav = tmp_path / "source.wav"
    ffmpeg_service.extract_audio(sample_video, str(out_wav), media_info.duration)
    return str(out_wav)


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


def test_cut_audio_produces_correct_duration(ffmpeg_binaries, extracted_source_wav, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_path = tmp_path / "cut.wav"

    service.cut_audio(extracted_source_wav, str(out_path), start=0.2, end=0.7)

    assert out_path.exists()
    assert _wav_duration(str(out_path)) == pytest.approx(0.5, abs=0.01)


def test_concat_audio_sums_durations(ffmpeg_binaries, extracted_source_wav, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    cut_a = tmp_path / "a.wav"
    cut_b = tmp_path / "b.wav"
    service.cut_audio(extracted_source_wav, str(cut_a), 0.0, 0.3)
    service.cut_audio(extracted_source_wav, str(cut_b), 0.3, 0.9)

    out_path = tmp_path / "merged.wav"
    service.concat_audio([str(cut_a), str(cut_b)], str(out_path))

    assert _wav_duration(str(out_path)) == pytest.approx(0.9, abs=0.01)


def test_concat_audio_rejects_empty_list(ffmpeg_binaries, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    with pytest.raises(ValueError):
        service.concat_audio([], str(tmp_path / "out.wav"))


def test_export_audio_wav(ffmpeg_binaries, extracted_source_wav, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_path = tmp_path / "export.wav"

    service.export_audio(extracted_source_wav, str(out_path), "wav", "16")

    assert out_path.exists()
    with wave.open(str(out_path), "rb") as wav_file:
        assert wav_file.getsampwidth() == 2


def test_export_audio_mp3(ffmpeg_binaries, extracted_source_wav, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    out_path = tmp_path / "export.mp3"

    service.export_audio(extracted_source_wav, str(out_path), "mp3", "192")

    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_export_audio_rejects_unknown_format(ffmpeg_binaries, extracted_source_wav, tmp_path):
    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    with pytest.raises(ValueError):
        service.export_audio(extracted_source_wav, str(tmp_path / "out.xyz"), "xyz", "1")
