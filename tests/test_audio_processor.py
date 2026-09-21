"""Tests de app.services.audio_processor."""

from pathlib import Path

import pytest

from app.models.audio_settings import AudioSettings
from app.services import sequence_service
from app.services.audio_processor import process_sequence, reset_processing
from app.services.ffmpeg_service import FFmpegService
from app.services.ffprobe_service import FFprobeService
from app.services.project_service import create_project_for_video


@pytest.fixture
def project_with_sequence(ffmpeg_binaries, sample_video):
    ffprobe_service = FFprobeService(ffmpeg_binaries.ffprobe_path)
    media_info = ffprobe_service.probe(sample_video)
    project = create_project_for_video(media_info)

    ffmpeg_service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    original_audio = str(Path(project.temp_dir) / "source.wav")
    ffmpeg_service.extract_audio(sample_video, original_audio, media_info.duration)
    project.original_audio_path = original_audio

    sequence = sequence_service.add_sequence(project, ffmpeg_service, 0.0, 0.8)
    return project, sequence, ffmpeg_service


def test_process_sequence_with_no_settings_returns_none(project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence

    result = process_sequence(project, sequence, ffmpeg_service)

    assert result is None
    assert sequence.processed_audio_path == ""
    assert sequence.effective_audio_path == sequence.audio_path


def test_process_sequence_applies_gain(project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    sequence.audio_settings = AudioSettings(gain=3.0)

    result = process_sequence(project, sequence, ffmpeg_service)

    assert result is not None
    assert Path(result).exists()
    assert sequence.processed_audio_path == result
    assert sequence.effective_audio_path == result
    # le fichier brut original n'est jamais écrasé
    assert Path(sequence.audio_path).exists()


def test_reset_processing_clears_settings_and_path(project_with_sequence):
    project, sequence, ffmpeg_service = project_with_sequence
    sequence.audio_settings = AudioSettings(gain=5.0)
    process_sequence(project, sequence, ffmpeg_service)
    assert sequence.processed_audio_path

    reset_processing(sequence)

    assert sequence.processed_audio_path == ""
    assert sequence.audio_settings == AudioSettings()
    assert sequence.effective_audio_path == sequence.audio_path


def test_peak_normalisation_measures_the_file_and_lands_on_the_target(ffmpeg_binaries, tmp_path, synthetic_wav_file):
    """Le WAV de test culmine à -4 dBFS environ : après normalisation il doit viser -1 dBFS."""
    from app.services.ffmpeg_service import FFmpegService

    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)
    before = service.measure_peak_db(synthetic_wav_file)
    assert -12.0 < before < 0.0

    out_path = tmp_path / "normalise.wav"
    service.apply_filters(
        synthetic_wav_file, str(out_path), f"volume={-1.0 - before:.2f}dB"
    )

    assert abs(service.measure_peak_db(str(out_path)) - (-1.0)) < 0.3


def test_measuring_an_unreadable_file_reports_full_scale(ffmpeg_binaries, tmp_path):
    from app.services.ffmpeg_service import FFmpegService

    service = FFmpegService(ffmpeg_binaries.ffmpeg_path)

    assert service.measure_peak_db(str(tmp_path / "absent.wav")) == 0.0
