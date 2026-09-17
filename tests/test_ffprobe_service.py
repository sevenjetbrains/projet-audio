"""Tests de FFprobeService."""

import pytest

from app.services.ffprobe_service import FFprobeService, ProbeError


def test_probe_returns_media_info(ffmpeg_binaries, sample_video):
    service = FFprobeService(ffmpeg_binaries.ffprobe_path)

    info = service.probe(sample_video)

    assert info.duration == pytest.approx(1.0, abs=0.2)
    assert info.resolution == (64, 64)
    assert info.audio_codec == "aac"
    assert info.sample_rate == 44100
    assert info.channels == 1
    assert info.size_bytes > 0


def test_probe_missing_file(ffmpeg_binaries):
    service = FFprobeService(ffmpeg_binaries.ffprobe_path)

    with pytest.raises(ProbeError, match="n'existe pas"):
        service.probe("this_file_does_not_exist.mp4")


def test_probe_unsupported_extension(ffmpeg_binaries, tmp_path):
    service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    fake_file = tmp_path / "video.txt"
    fake_file.write_text("not a video")

    with pytest.raises(ProbeError, match="n'est pas supporté"):
        service.probe(str(fake_file))


def test_probe_corrupted_file(ffmpeg_binaries, tmp_path):
    service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    fake_file = tmp_path / "corrupted.mp4"
    fake_file.write_bytes(b"not a real video file")

    with pytest.raises(ProbeError):
        service.probe(str(fake_file))
