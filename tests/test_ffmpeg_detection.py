"""Tests de la détection ffmpeg/ffprobe."""

import pytest

from app.config.settings import FFmpegNotFoundError, find_ffmpeg_binaries


def test_find_ffmpeg_binaries_success():
    binaries = find_ffmpeg_binaries()
    assert binaries.ffmpeg_path
    assert binaries.ffprobe_path


def test_find_ffmpeg_binaries_missing(monkeypatch):
    monkeypatch.setattr("app.config.settings.shutil.which", lambda name: None)

    with pytest.raises(FFmpegNotFoundError) as exc_info:
        find_ffmpeg_binaries()

    assert "ffmpeg" in str(exc_info.value)
    assert "ffprobe" in str(exc_info.value)
