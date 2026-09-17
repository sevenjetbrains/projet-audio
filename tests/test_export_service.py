"""Tests de app.services.export_service."""

from pathlib import Path

import pytest

from app.services import sequence_service
from app.services.export_service import ExportError, export_project, merge_sequences
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video


@pytest.fixture
def project_with_sequences(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.3)
    sequence_service.add_sequence(project, ffmpeg_service, 0.3, 0.9)

    return project, ffmpeg_service


def test_merge_sequences_requires_at_least_one(ffmpeg_binaries):
    from app.models.media import MediaInfo

    project = create_project_for_video(
        MediaInfo(
            path="x.mp4", duration=1.0, container_format="mp4", video_codec="h264",
            audio_codec="aac", sample_rate=44100, channels=1, resolution=None,
            bitrate=None, size_bytes=1,
        )
    )
    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    with pytest.raises(ExportError):
        merge_sequences(project, ffmpeg_service)


def test_merge_sequences_produces_final_wav(project_with_sequences):
    project, ffmpeg_service = project_with_sequences

    final_wav = merge_sequences(project, ffmpeg_service)

    assert Path(final_wav).exists()
    assert Path(final_wav).stat().st_size > 0


def test_export_project_wav(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences
    out_path = tmp_path / "final.wav"

    export_project(project, ffmpeg_service, str(out_path), "WAV", "16")

    assert out_path.exists()


def test_export_project_mp3(project_with_sequences, tmp_path):
    project, ffmpeg_service = project_with_sequences
    out_path = tmp_path / "final.mp3"

    export_project(project, ffmpeg_service, str(out_path), "MP3", "192")

    assert out_path.exists()


def test_merge_sequences_with_crossfade(project_with_sequences):
    project, ffmpeg_service = project_with_sequences
    project.crossfade_duration = 0.1

    final_wav = merge_sequences(project, ffmpeg_service)

    assert Path(final_wav).exists()
    assert Path(final_wav).stat().st_size > 0
